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
    line_spacing: float = 1.2
    alignment: str = "center"  # "left", "center", "right"
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

    @staticmethod
    def _line_ink_extent(font: ImageFont.FreeTypeFont, line: str, stroke_width: int = 0) -> Tuple[int, int]:
        """
        Left and right edge of the ink a line draws at x=0. Font boxes include each glyph's
        side bearings (a "1" in Arial has much more space on its left), so centring on the box
        puts the ink off-centre.
        """
        advance = int(font.getlength(line)) + 2 * stroke_width
        pad = 8 + 2 * stroke_width
        height = max(font.getbbox(line, anchor="lt")[3], 1) + 2 * pad
        probe = Image.new("L", (advance + 2 * pad, height), 0)
        ImageDraw.Draw(probe).text(
            (pad, pad), line, font=font, fill=255, anchor="lt",
            stroke_width=stroke_width, stroke_fill=255,
        )
        bbox = probe.getbbox()
        if not bbox:
            return 0, 0
        # Leading spaces are typed indentation, so they count as part of the line
        indent = int(round(font.getlength(line[: len(line) - len(line.lstrip(" "))])))
        return bbox[0] - pad - indent, bbox[2] - pad

    def calculate_multiline_dims(
        self, lines: List[str], font: ImageFont.FreeTypeFont, line_spacing: float, stroke_width: int = 0
    ) -> Tuple[int, int, List[int]]:
        """Calculates total ink width, height and individual line heights for multiline text."""
        if not lines:
            return 0, 0, []
        sample_bbox = font.getbbox("".join(lines) or "Ag", anchor="lt")
        base_line_height = max(sample_bbox[3] - sample_bbox[1], 1)
        line_spacing_px = base_line_height * line_spacing
        max_width = 0
        line_heights = []

        for line in lines:
            if line.strip():
                left, right = self._line_ink_extent(font, line, stroke_width)
                w = right - left
            else:
                w = 0
            max_width = max(max_width, w)
            line_heights.append(base_line_height)

        n = len(lines)
        total_height = base_line_height * n
        if n > 1:
            total_height += int(round((line_spacing_px - base_line_height) * (n - 1)))

        return max_width, total_height, line_heights

    def compute_auto_font_size(
        self, lines: List[str], font_identifier: str, target_height: int, line_spacing: float
    ) -> Tuple[int, ImageFont.FreeTypeFont, float]:
        """Calculates the maximum font size that fits into target printable height."""
        low = 6
        high = target_height * 2
        best_size = low
        best_font = font_manager.load_font(font_identifier, low)
        adjusted_spacing = line_spacing

        # Binary search for optimal font size
        while low <= high:
            mid = (low + high) // 2
            test_font = font_manager.load_font(font_identifier, mid)
            _, h, _ = self.calculate_multiline_dims(lines, test_font, line_spacing)

            if h <= target_height:
                best_size = mid
                best_font = test_font
                low = mid + 1
            else:
                high = mid - 1

        # Fine-tune line spacing if multiline
        if len(lines) > 1:
            test_h = self.calculate_multiline_dims(lines, best_font, adjusted_spacing)[1]
            if test_h > target_height:
                # Try slightly tighter line spacing down to 0.85x
                min_spacing = line_spacing * 0.85
                step = 0.02
                cur_spacing = line_spacing
                while cur_spacing >= min_spacing:
                    cur_spacing -= step
                    if self.calculate_multiline_dims(lines, best_font, cur_spacing)[1] <= target_height:
                        adjusted_spacing = cur_spacing
                        break

        return best_size, best_font, adjusted_spacing

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

        # 1. Parse text lines
        raw_text = config.text.replace("\\n", "\n")
        lines = raw_text.split("\n")

        # 2. Determine font and size
        if config.auto_fit_font:
            base_size, font, spacing = self.compute_auto_font_size(
                lines, config.font_name, printable_h, config.line_spacing
            )
            if abs(config.font_scale - 100.0) > 0.5:
                effective_size = max(int(round(base_size * (config.font_scale / 100.0))), 6)
                font = font_manager.load_font(config.font_name, effective_size)
            else:
                effective_size = base_size
        else:
            effective_size = max(config.fixed_font_size, 6)
            if abs(config.font_scale - 100.0) > 0.5:
                effective_size = max(int(round(effective_size * (config.font_scale / 100.0))), 6)
            font = font_manager.load_font(config.font_name, effective_size)
            spacing = config.line_spacing

        text_w, text_h, _ = self.calculate_multiline_dims(lines, font, spacing, config.stroke_width)
        self._last_text_overflow = text_h > printable_h

        # 3. Handle QR Code
        qr_img = None
        if config.qr_enabled and config.qr_data.strip():
            qr_img = self.generate_qr_image(config.qr_data, printable_h, config.qr_scale)

        # 4. Handle Merged Image
        merged_img = None
        if config.image_path:
            merged_img = self.process_user_image(
                config.image_path, printable_h, config.image_scale, config.white_level
            )

        # 5. Compute content layout width
        gap = 12
        total_content_w = config.h_padding * 2

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

        has_text = any(line.strip() for line in lines)
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

        cur_x = config.h_padding

        for el in elements_left:
            y_pos = print_border + (printable_h - el.height) // 2
            img_canvas.paste(el, (cur_x, y_pos))
            cur_x += el.width + gap

        if has_text:
            y_text = print_border + (printable_h - text_h) // 2 + config.v_shift
            sample_bbox = font.getbbox("".join(lines) or "Ag", anchor="lt")
            base_lh = max(sample_bbox[3] - sample_bbox[1], 1)
            line_step = base_lh * spacing

            current_line_y = y_text
            for line in lines:
                if line.strip():
                    ink_left, ink_right = self._line_ink_extent(font, line, config.stroke_width)
                    lw = ink_right - ink_left
                    if config.alignment == "center":
                        line_x = cur_x + (text_w - lw) // 2
                    elif config.alignment == "right":
                        line_x = cur_x + (text_w - lw)
                    else:
                        line_x = cur_x

                    # Shift by the ink's own offset so the ink, not the font box, lands at line_x
                    draw.text(
                        (line_x - ink_left, current_line_y),
                        line,
                        font=font,
                        fill="black",
                        anchor="lt",
                        stroke_width=config.stroke_width,
                        stroke_fill=config.stroke_fill or "black",
                    )
                current_line_y += line_step

            cur_x += text_w + gap

        for el in elements_right:
            y_pos = print_border + (printable_h - el.height) // 2
            img_canvas.paste(el, (cur_x, y_pos))
            cur_x += el.width + gap

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
        self, configs: List[LabelConfig], gap_dots: int = BATCH_GAP_DOTS
    ) -> Tuple[Image.Image, Image.Image, bytes, LabelMetrics]:
        """
        Renders a continuous batch chain of multiple labels with dotted cut lines in between,
        eliminating the ~25mm wasted tape between consecutive individual prints.
        Every label gets the same half-gap of tape on both sides, first and last included.
        The strip starts with a cut line; its end needs none, since it stops at the cutter.
        """
        if not configs:
            return self.render(LabelConfig(text=""))
        if len(configs) == 1:
            return self.render(configs[0])

        canvases = []
        specs = []
        borders = []
        printable_hs = []

        for cfg in configs:
            c, spec, p_border, p_h, _, _ = self._render_base_canvas(cfg)
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
