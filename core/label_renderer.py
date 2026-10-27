#!/usr/bin/env python3
"""
Label rendering engine for Brother PT-P300BT.
Generates both photorealistic tape previews and 128-dot 1-bit raster payloads for the printer.
"""

import io
import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from PIL import Image, ImageDraw, ImageFont, ImageOps
import qrcode

from core import rich_text
from core.font_manager import font_manager
from core.specs import (
    DOT_PITCH_MM,
    INVENTORY_TAPE_WIDTH_MM,
    PRINTHEAD_DOTS,
    TAPE_LEAD_MM,
    TAPE_SPECS,
    get_tape_spec,
)


@dataclass
class LabelMetrics:
    """Label physical dimensions and print timing estimates."""
    content_width_dots: int = 0
    raster_lines: int = 0
    print_length_mm: float = 0.0
    print_length_cm: float = 0.0
    print_length_in: float = 0.0
    total_used_length_mm: float = 0.0
    print_duration_sec: float = 0.0
    effective_font_size: int = 0
    tape_saved_mm: float = 0.0
    label_count: int = 1
    warning: Optional[str] = None


@dataclass
class LabelConfig:
    """Configuration options for rendering a label."""
    # Text
    text: str = "Label Text"
    font_name: str = "Arial"
    auto_fit_font: bool = True
    fixed_font_size: int = 40
    font_scale: float = 100.0  # Percentage (10-200)
    text_height_mm: Optional[float] = None  # Height of a capital letter; None sizes the text as above
    line_spacing: float = 1.2
    alignment: str = "center"  # "left", "center", "right"; a line can override it (see core/rich_text.py)
    stroke_width: int = 0
    stroke_fill: Optional[str] = None
    h_padding: int = 8  # dots
    v_shift: int = 0  # dots

    @property
    def h_padding_dots(self) -> int:
        return self.h_padding

    @h_padding_dots.setter
    def h_padding_dots(self, value: int):
        self.h_padding = value
    
    frame: str = "none"  # "none", "box", "rounded"

    # Sizing & Stretching
    fixed_width_mm: Optional[float] = None
    end_margin: int = 0  # dots
    
    # QR Code & Barcode
    qr_enabled: bool = False
    qr_data: str = ""
    qr_position: str = "left"  # "left", "right", "standalone"
    qr_scale: float = 1.0  # relative to printable height
    
    # Image / Icon Merge
    image_path: Optional[str] = None
    image_position: str = "left"  # "left", "right", "standalone"
    image_scale: float = 1.0
    image_x_offset: int = 0
    image_y_offset: int = 0
    white_level: int = 240
    threshold: int = 100
    
    # Colors & Tape Physical Attributes
    tape_width_mm: float = 12.0
    tape_bg_color: str = "#FFFFFF"  # Background color for preview
    tape_fg_color: str = "#000000"  # Text/drawing color
    show_guides: bool = False  # Show printable area and tape guides
    show_rulers: bool = False  # Show mm/inch rulers

    # Cut lines: the app prints its own dotted cut lines at both ends of every label,
    # in place of the ":" cut mark the printer adds when it gets the auto-cut flag
    cut_line: bool = True  # Print vertical cut lines on the tape
    cut_line_style: str = "dotted"  # "dotted", "solid", "ticks"
    cut_line_position: str = "start"  # "start", "end", "both"; the end needs none, it lines up with the cutter
    auto_cut_hardware: bool = False  # Hardware auto-cut flag; the PT-P300BT only prints a ":" mark for it

    # Hardware Inventory Design System (V2)
    inventory_config: Optional[object] = None  # FastenerLabelConfig or ComponentLabelConfig


# A frame is drawn this thick, with this much space between it and the content
FRAME_WIDTH_DOTS = 2
FRAME_GAP_DOTS = 3

# Tape between labels in a batch; each label gets half of it on both sides (14 dots ≈ 2 mm)
BATCH_GAP_DOTS = 28
# Blank tape on each side of a single bin label, which is otherwise drawn border to border
SINGLE_BIN_PADDING_MM = 1.0


class LabelRenderer:
    """Core renderer for Brother PT-P300BT labels."""

    DOT_PITCH_MM = DOT_PITCH_MM
    PRINTHEAD_DOTS = PRINTHEAD_DOTS
    TAPE_SPECS = TAPE_SPECS
    MAX_TOTAL_LENGTH_MM = 499.0

    def __init__(self):
        pass

    def _get_tape_spec(self, tape_width_mm: float) -> dict:
        return get_tape_spec(tape_width_mm)

    def generate_qr_image(self, data: str, target_height: int, scale: float = 1.0) -> Optional[Image.Image]:
        """Generates a high-contrast QR code image sized to printable height."""
        if not data.strip():
            return None
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=4,
            border=1,
        )
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white").convert("L")
        
        # Scale to target height
        side = max(int(target_height * scale), 8)
        return img.resize((side, side), Image.Resampling.NEAREST)

    def process_user_image(
        self, image_path: str, target_height: int, scale: float = 1.0, white_level: int = 240
    ) -> Optional[Image.Image]:
        """Loads and crops white space from a user image, resizing to fit printable height."""
        try:
            raw_img = Image.open(image_path).convert("RGBA")
        except Exception:
            return None

        # Composite against white background
        bg = Image.new("RGBA", raw_img.size, (255, 255, 255, 255))
        bg.paste(raw_img, (0, 0), raw_img)
        gray = bg.convert("L")

        # Find content bounding box (pixels darker than white_level)
        content_mask = gray.point(lambda p: 255 if p < white_level else 0)
        bbox = content_mask.getbbox()

        if bbox:
            cropped = gray.crop(bbox)
            aspect = cropped.width / cropped.height
            new_h = int(target_height * scale)
            new_w = max(int(new_h * aspect), 1)
            return cropped.resize((new_w, new_h), Image.Resampling.LANCZOS)
        else:
            return None

    def _render_base_canvas(
        self, config: LabelConfig
    ) -> Tuple[Image.Image, dict, int, int, int, int]:
        """Renders raw content onto grayscale base canvas without trailing cut lines."""
        is_inventory = getattr(config, "inventory_config", None) is not None
        self._last_text_overflow = False
        # Hardware inventory layouts are designed for 64 printable dots, so they always use 12 mm tape
        spec = self._get_tape_spec(INVENTORY_TAPE_WIDTH_MM if is_inventory else config.tape_width_mm)
        printable_h = spec["printable_height"]
        tape_h = spec["tape_height"]
        canvas_h = spec["canvas_height"]
        print_border = (canvas_h - printable_h) // 2

        # Hardware Inventory System V2 rendering
        if is_inventory:
            from core.inventory_renderer import inventory_renderer, FastenerLabelConfig
            if isinstance(config.inventory_config, FastenerLabelConfig):
                inv_img = inventory_renderer.render_fastener(config.inventory_config)
            else:
                inv_img = inventory_renderer.render_component(config.inventory_config)
            inv_w, inv_h = inv_img.size
            img_canvas = Image.new("RGB", (inv_w, canvas_h), "white")
            img_canvas.paste(inv_img.convert("RGB"), (0, print_border))
            return img_canvas, spec, print_border, printable_h, canvas_h, 16

        # 1. Parse the styled text and leave room for a frame
        doc = rich_text.parse(config.text)
        frame_inset = FRAME_WIDTH_DOTS + FRAME_GAP_DOTS if config.frame in ("box", "rounded") else 0
        inner_h = printable_h - 2 * frame_inset
        # Rounded corners cut into the sides, so keep the content further in
        frame_inset_x = frame_inset + (printable_h // 8 if config.frame == "rounded" else 0)
        layout = rich_text.TextLayout(
            doc, config.font_name, config.stroke_width, config.line_spacing, config.alignment
        )

        # 2. Determine font size. A letter height in mm is exact, so Text scale leaves it alone.
        if config.text_height_mm:
            effective_size = layout.size_for_cap_height(config.text_height_mm / self.DOT_PITCH_MM)
        elif config.auto_fit_font:
            effective_size = layout.fit_size(inner_h)
        else:
            effective_size = max(config.fixed_font_size, 6)
        if not config.text_height_mm and abs(config.font_scale - 100.0) > 0.5:
            effective_size = max(int(round(effective_size * (config.font_scale / 100.0))), 6)

        has_text = doc.has_text
        text_img = layout.render(effective_size) if has_text else None
        text_w = text_img.width if text_img else 0
        text_h = text_img.height if text_img else 0
        self._last_text_overflow = text_h > inner_h

        # 3. Handle QR Code
        qr_img = None
        if config.qr_enabled and config.qr_data.strip():
            qr_img = self.generate_qr_image(config.qr_data, inner_h, config.qr_scale)

        # 4. Handle Merged Image
        merged_img = None
        if config.image_path:
            merged_img = self.process_user_image(
                config.image_path, inner_h, config.image_scale, config.white_level
            )

        # 5. Compute content layout width
        gap = 12
        total_content_w = config.h_padding * 2 + 2 * frame_inset_x

        elements_left = []
        elements_right = []

        if qr_img:
            if config.qr_position == "left":
                elements_left.append(qr_img)
            elif config.qr_position == "right":
                elements_right.append(qr_img)

        if merged_img:
            if config.image_position == "left":
                elements_left.append(merged_img)
            elif config.image_position == "right":
                elements_right.append(merged_img)

        for el in elements_left + elements_right:
            total_content_w += el.width + gap

        if has_text:
            total_content_w += text_w
        elif not elements_left and not elements_right:
            total_content_w += 20

        total_content_w += config.end_margin

        if config.fixed_width_mm:
            target_dots = int(round(config.fixed_width_mm / self.DOT_PITCH_MM))
            if target_dots > total_content_w:
                total_content_w = target_dots

        # 6. Create working canvas
        img_canvas = Image.new("RGB", (max(total_content_w, 10), canvas_h), "white")
        draw = ImageDraw.Draw(img_canvas)

        cur_x = config.h_padding + frame_inset_x

        for el in elements_left:
            y_pos = print_border + (printable_h - el.height) // 2
            img_canvas.paste(el, (cur_x, y_pos))
            cur_x += el.width + gap

        if text_img is not None:
            y_text = print_border + (printable_h - text_h) // 2 + config.v_shift
            img_canvas.paste("black", (cur_x, y_text), text_img)
            cur_x += text_w + gap

        for el in elements_right:
            y_pos = print_border + (printable_h - el.height) // 2
            img_canvas.paste(el, (cur_x, y_pos))
            cur_x += el.width + gap

        if frame_inset:
            box = [
                config.h_padding,
                print_border,
                img_canvas.width - config.h_padding - config.end_margin - 1,
                print_border + printable_h - 1,
            ]
            if config.frame == "rounded":
                draw.rounded_rectangle(box, radius=printable_h // 4, outline="black", width=FRAME_WIDTH_DOTS)
            else:
                draw.rectangle(box, outline="black", width=FRAME_WIDTH_DOTS)

        return img_canvas, spec, print_border, printable_h, canvas_h, effective_size

    def render(
        self, config: LabelConfig
    ) -> Tuple[Image.Image, Image.Image, bytes, LabelMetrics]:
        """
        Renders a single label based on configuration.
        Returns: (preview_image, raster_128_image, raster_bytes, metrics)
        """
        img_canvas, spec, print_border, printable_h, canvas_h, effective_size = (
            self._render_base_canvas(config)
        )

        # A label gets the same half-gap of tape as a label in a batch, so single and
        # queued prints look alike. Bin labels are drawn border to border, so without
        # cut lines they still get a little blank tape on each side.
        pad = 0
        if config.cut_line:
            pad = BATCH_GAP_DOTS // 2
        elif getattr(config, "inventory_config", None) is not None:
            pad = int(round(SINGLE_BIN_PADDING_MM / self.DOT_PITCH_MM))
        if pad:
            padded = Image.new("RGB", (img_canvas.width + 2 * pad, img_canvas.height), "white")
            padded.paste(img_canvas, (pad, 0))
            img_canvas = padded

        draw = ImageDraw.Draw(img_canvas)

        if config.cut_line:
            cut_positions = []
            if config.cut_line_position in ("both", "start"):
                cut_positions.append(0)
            if config.cut_line_position in ("both", "end"):
                cut_positions.append(img_canvas.width - 1)

            for cx in cut_positions:
                if config.cut_line_style == "dotted":
                    for cy in range(print_border, print_border + printable_h, 4):
                        draw.line([(cx, cy), (cx, cy + 1)], fill="black", width=1)
                elif config.cut_line_style == "solid":
                    draw.line([(cx, print_border), (cx, print_border + printable_h - 1)], fill="black", width=1)
                elif config.cut_line_style == "ticks":
                    tlen = 8
                    draw.line([(cx, print_border), (cx, print_border + tlen)], fill="black", width=1)
                    draw.line([(cx, print_border + printable_h - tlen), (cx, print_border + printable_h - 1)], fill="black", width=1)

        # 7. Generate 128-dot 1-bit binary raster image
        rotated = ImageOps.invert(
            img_canvas.convert("L", dither=Image.Dither.FLOYDSTEINBERG).rotate(
                -90, expand=True, resample=Image.Resampling.BICUBIC
            )
        )
        rotated = ImageOps.mirror(rotated)
        bin_image = rotated.point(lambda p: 255 if p > config.threshold else 0)
        binary_img = bin_image.convert("1")

        bw, bh = binary_img.size
        padded_128 = Image.new("1", (self.PRINTHEAD_DOTS, bh))
        pad_x = (self.PRINTHEAD_DOTS - bw) // 2
        padded_128.paste(binary_img, (pad_x, 0))
        raster_bytes = padded_128.tobytes()

        # 8. Photorealistic Preview
        preview_img = self._create_photorealistic_preview(img_canvas, config, spec, print_border)

        # 9. Metrics
        raster_lines = padded_128.size[1]
        print_len_mm = raster_lines * self.DOT_PITCH_MM
        total_used_mm = print_len_mm + TAPE_LEAD_MM
        print_dur = print_len_mm / 20.0

        warning = None
        if total_used_mm > self.MAX_TOTAL_LENGTH_MM:
            warning = "Label exceeds maximum print length (49.9 cm / 19.6 in)"
        elif getattr(self, "_last_text_overflow", False) and config.text_height_mm:
            warning = (f"Text at {config.text_height_mm:g} mm is taller than this tape prints and will be "
                       "clipped. Pick a smaller size or fewer lines.")
        elif getattr(self, "_last_text_overflow", False) and not config.auto_fit_font:
            warning = "Text is taller than the printable area and will be clipped. Reduce the font size."

        metrics = LabelMetrics(
            content_width_dots=img_canvas.width,
            raster_lines=raster_lines,
            print_length_mm=round(print_len_mm, 1),
            print_length_cm=round(print_len_mm / 10.0, 2),
            print_length_in=round(print_len_mm / 25.4, 2),
            total_used_length_mm=round(total_used_mm, 1),
            print_duration_sec=round(print_dur, 1),
            effective_font_size=effective_size,
            tape_saved_mm=0.0,
            label_count=1,
            warning=warning,
        )

        return preview_img, padded_128, raster_bytes, metrics

    def render_batch(
        self, configs: List[LabelConfig], gap_dots: int = BATCH_GAP_DOTS,
        spans: Optional[List[Tuple[int, int]]] = None,
    ) -> Tuple[Image.Image, Image.Image, bytes, LabelMetrics]:
        """
        Renders a continuous batch chain of multiple labels with dotted cut lines in between,
        eliminating the ~25mm wasted tape between consecutive individual prints.
        Every label gets the same half-gap of tape on both sides, first and last included.
        The strip starts with a cut line; its end needs none, since it stops at the cutter.
        A list passed as spans gets each label's (start, end) x in the preview. The same
        config object passed more than once (copies) is drawn once.
        """
        if not configs:
            return self.render(LabelConfig(text=""))
        if len(configs) == 1:
            result = self.render(configs[0])
            if spans is not None:
                spans.append((0, result[0].width))
            return result

        canvases = []
        specs = []
        borders = []
        printable_hs = []
        drawn = {}

        for cfg in configs:
            if id(cfg) not in drawn:
                drawn[id(cfg)] = self._render_base_canvas(cfg)
            c, spec, p_border, p_h, _, _ = drawn[id(cfg)]
            canvases.append(c)
            specs.append(spec)
            borders.append(p_border)
            printable_hs.append(p_h)

        spec = specs[0]
        canvas_h = spec["canvas_height"]
        print_border = borders[0]
        printable_h = printable_hs[0]

        # Total stitched width: half a gap before the first and after the last label
        margin = gap_dots // 2
        total_w = sum(c.width for c in canvases) + gap_dots * (len(canvases) - 1) + 2 * margin
        batch_canvas = Image.new("RGB", (max(total_w, 10), canvas_h), "white")
        draw = ImageDraw.Draw(batch_canvas)

        def cut_line(x: int):
            for cy in range(print_border, print_border + printable_h, 4):
                draw.line([(x, cy), (x, cy + 1)], fill="black", width=1)

        cut_line(0)
        cur_x = margin
        for idx, c in enumerate(canvases):
            batch_canvas.paste(c, (cur_x, 0))
            if spans is not None:
                spans.append((cur_x, cur_x + c.width))
            cur_x += c.width
            if idx < len(canvases) - 1:
                cut_line(cur_x + margin)
                cur_x += gap_dots

        # 128-dot raster transformation
        rotated = ImageOps.invert(
            batch_canvas.convert("L", dither=Image.Dither.FLOYDSTEINBERG).rotate(
                -90, expand=True, resample=Image.Resampling.BICUBIC
            )
        )
        rotated = ImageOps.mirror(rotated)
        threshold = configs[0].threshold
        bin_image = rotated.point(lambda p: 255 if p > threshold else 0)
        binary_img = bin_image.convert("1")

        bw, bh = binary_img.size
        padded_128 = Image.new("1", (self.PRINTHEAD_DOTS, bh))
        pad_x = (self.PRINTHEAD_DOTS - bw) // 2
        padded_128.paste(binary_img, (pad_x, 0))
        raster_bytes = padded_128.tobytes()

        # Preview
        preview_img = self._create_photorealistic_preview(
            batch_canvas, configs[0], spec, print_border
        )

        # Metrics & tape savings
        raster_lines = padded_128.size[1]
        print_len_mm = raster_lines * self.DOT_PITCH_MM
        total_used_mm = print_len_mm + TAPE_LEAD_MM  # Only ONE lead-in + trail
        tape_saved_mm = TAPE_LEAD_MM * (len(configs) - 1)
        print_dur = print_len_mm / 20.0

        warning = None
        if total_used_mm > self.MAX_TOTAL_LENGTH_MM:
            warning = "Batch chain exceeds 49.9 cm. You may need to split it into two batches."

        metrics = LabelMetrics(
            content_width_dots=batch_canvas.width,
            raster_lines=raster_lines,
            print_length_mm=round(print_len_mm, 1),
            print_length_cm=round(print_len_mm / 10.0, 2),
            print_length_in=round(print_len_mm / 25.4, 2),
            total_used_length_mm=round(total_used_mm, 1),
            print_duration_sec=round(print_dur, 1),
            effective_font_size=0,
            tape_saved_mm=round(tape_saved_mm, 1),
            label_count=len(configs),
            warning=warning,
        )

        return preview_img, padded_128, raster_bytes, metrics

    def _create_photorealistic_preview(
        self,
        base_canvas: Image.Image,
        config: LabelConfig,
        spec: dict,
        print_border: int,
    ) -> Image.Image:
        """Renders photorealistic colored preview with tape cartridge appearance and guides."""
        w, h = base_canvas.size
        tape_bg = config.tape_bg_color or "#FFFFFF"
        tape_fg = config.tape_fg_color or "#000000"

        # Convert grayscale base canvas (where text is black on white) to custom colors
        gray = base_canvas.convert("L")
        
        # Colorize: black in base becomes tape_fg, white becomes tape_bg
        colorized = ImageOps.colorize(gray, black=tape_fg, white=tape_bg)
        preview = colorized.convert("RGBA")
        draw = ImageDraw.Draw(preview)

        # Draw guides if requested
        if config.show_guides:
            # Printable area top/bottom dotted lines (red)
            for x in range(0, w, 6):
                draw.line(
                    [(x, print_border - 1), (x + 3, print_border - 1)],
                    fill=(230, 57, 70, 220),
                    width=1,
                )
                draw.line(
                    [(x, h - print_border), (x + 3, h - print_border)],
                    fill=(230, 57, 70, 220),
                    width=1,
                )

            # Tape boundary cyan lines
            tape_border = (h - spec["tape_height"]) // 2
            if tape_border > 0:
                draw.line([(0, tape_border), (w, tape_border)], fill=(0, 180, 216, 200), width=1)
                draw.line([(0, h - tape_border), (w, h - tape_border)], fill=(0, 180, 216, 200), width=1)

        # Draw rulers if requested
        if config.show_rulers:
            ruler_font = font_manager.load_font("Arial", 8)
            # mm ticks (1 mm ≈ 6.71 dots)
            dots_per_mm = 1.0 / self.DOT_PITCH_MM
            x = 0.0
            mm_val = 0
            while x < w:
                ix = int(round(x))
                tick_len = 6 if mm_val % 10 == 0 else (4 if mm_val % 5 == 0 else 2)
                draw.line([(ix, 0), (ix, tick_len)], fill=(120, 120, 120, 220), width=1)
                draw.line([(ix, h - 1), (ix, h - 1 - tick_len)], fill=(120, 120, 120, 220), width=1)
                if mm_val > 0 and mm_val % 10 == 0:
                    draw.text((ix + 2, 1), f"{mm_val//10}cm", font=ruler_font, fill=(100, 100, 100, 220))
                x += dots_per_mm
                mm_val += 1

        return preview
