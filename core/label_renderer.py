#!/usr/bin/env python3
"""
Label rendering engine for Brother PT-P300BT.
Generates both photorealistic tape previews and 128-dot 1-bit raster payloads for the printer.
"""

import dataclasses
import io
import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from PIL import Image, ImageDraw, ImageFont, ImageOps
import qrcode

from core import barcode

from core import rich_text
from core import borders
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
    max_text_height_mm: Optional[float] = None  # Tallest capital letter the text fits the tape at
    text_height_fell_back: bool = False  # The text_height_mm preset didn't fit, so the text was fitted


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
    text_height_fallback: bool = False  # Fit the text instead when text_height_mm is too tall for the tape
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
    
    frame: str = "none"  # a border from core/borders.py: "none", "box", "rounded", "wave", "stars"...
    # "horizontal"; "vertical", each letter upright under the one before, for tape stuck on
    # upright; or "turned", the whole text a quarter turn round, across the tape
    direction: str = "horizontal"

    # Sizing & Stretching
    fixed_width_mm: Optional[float] = None
    end_margin: int = 0  # dots
    
    # QR Code & Barcode
    qr_enabled: bool = False
    qr_data: str = ""
    qr_position: str = "left"  # "left", "right", "standalone"
    qr_scale: float = 1.0  # relative to printable height
    barcode_enabled: bool = False
    barcode_data: str = ""
    barcode_show_text: bool = True  # The code in plain text under the bars
    barcode_position: str = "left"  # "left", "right"
    barcode_scale: float = 1.0  # relative to printable height
    
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

    # Cut lines: the app prints its own cut marks at both ends of every label,
    # in place of the ":" cut mark the printer adds when it gets the auto-cut flag
    cut_line: bool = True  # Print vertical cut lines on the tape
    cut_line_style: str = "ticks"  # "ticks" (marks at the top and bottom edges only), "dotted", "solid"
    cut_line_position: str = "start"  # "start", "end", "both"; the end needs none, it lines up with the cutter
    auto_cut_hardware: bool = False  # Hardware auto-cut flag; the PT-P300BT only prints a ":" mark for it

    # Hardware Inventory Design System (V2)
    inventory_config: Optional[object] = None  # FastenerLabelConfig or ComponentLabelConfig

    # Kind of text label: "text"; "ports", one strip with a number or name over each port of a
    # patch panel or switch; or "flag", the text twice with room between to fold round a cable
    layout: str = "text"

    # Port strip: the ports are port_pitch_mm apart, exactly, and numbered from port_first
    port_count: int = 12
    port_pitch_mm: float = 19.0
    port_first: int = 1
    port_prefix: str = ""  # before each number, as A for A1, A2...
    port_use_names: bool = False  # port_names instead of numbers
    port_names: str = ""  # one per line; an empty line leaves its port blank
    port_divider_every: int = 0  # a thicker divider after every this many ports; 0 for none

    # Cable flag: each side is the label's text (flag_side_mm long, or as long as it needs), and
    # the tape between them goes once round a cable this thick
    flag_cable_mm: float = 6.0
    flag_side_mm: Optional[float] = None
    flag_fold_marks: bool = True


# Port strip dividers, and the room kept between a port's text and its dividers
PORT_DIVIDER_DOTS = 2
PORT_THICK_DIVIDER_DOTS = 5
PORT_TEXT_MARGIN_DOTS = 8
PORT_TEXT_V_MARGIN_DOTS = 4
# How far the marks where a cable flag folds reach in from the edges of the print
FLAG_MARK_DOTS = 8

# Length of the marks of a "ticks" cut line at the top and bottom of the printable area (about 0.85 mm)
CUT_TICK_DOTS = 6


def draw_cut_line(draw: ImageDraw.ImageDraw, x: int, top: int, height: int, style: str = "ticks") -> None:
    """
    Draws a cut line at column x of the printable area. Ticks only mark its two edges, so a cut
    that misses the line by a little leaves no shadow down the side of the label.
    """
    if style == "dotted":
        for y in range(top, top + height, 4):
            draw.line([(x, y), (x, y + 1)], fill="black", width=1)
    elif style == "solid":
        draw.line([(x, top), (x, top + height - 1)], fill="black", width=1)
    else:
        draw.line([(x, top), (x, top + CUT_TICK_DOTS - 1)], fill="black", width=1)
        draw.line([(x, top + height - CUT_TICK_DOTS), (x, top + height - 1)], fill="black", width=1)


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

    def generate_barcode_image(
        self, data: str, target_height: int, scale: float = 1.0, show_text: bool = True,
        font_name: str = "Arial",
    ) -> Optional[Image.Image]:
        """A Code 128 barcode as tall as the printable height times scale, or None."""
        height = min(max(int(target_height * scale), 8), target_height)
        font = font_manager.load_font(font_name, 12) if show_text else None
        return barcode.render(data, height, show_text, font)

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
        self._max_text_height_mm = None
        self._text_height_fell_back = False
        self._cut_off_mm = 0.0
        self._barcode_bad_chars = ""
        self._cut_off_at_mm = config.fixed_width_mm
        if config.layout == "flag" and not is_inventory:
            return self._render_cable_flag(config)
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

        if config.layout == "ports":
            return self._render_port_strip(config, spec, print_border, printable_h, canvas_h)

        # 1. Parse the styled text and leave room for a frame
        doc = rich_text.parse(config.text)
        border = borders.get(config.frame)
        inset_x, inset_y = border.insets(printable_h)
        frame_inset = inset_y
        inner_h = printable_h - 2 * frame_inset
        frame_inset_x = inset_x
        layout = rich_text.TextLayout(
            doc, config.font_name, config.stroke_width, config.line_spacing, config.alignment
        )

        # 2. Determine font size. A letter height in mm is exact, so Text scale leaves it alone,
        # unless it is a preset that is too tall for this text and tape: then the text fits instead.
        if config.direction in ("vertical", "turned") and doc.has_text:
            return self._render_turned_text(config, doc, layout, border, spec, print_border, printable_h, canvas_h)
        fit_size = layout.fit_size(inner_h)
        # Without text there is nothing to be too tall (the layout then measures a stand-in "Ag")
        if doc.has_text:
            self._max_text_height_mm = layout.cap_height(fit_size) * self.DOT_PITCH_MM
        text_height_mm = config.text_height_mm
        if text_height_mm:
            effective_size = layout.size_for_cap_height(text_height_mm / self.DOT_PITCH_MM)
            if config.text_height_fallback and doc.has_text and effective_size > fit_size:
                self._text_height_fell_back = True
                text_height_mm = None
                effective_size = fit_size
        elif config.auto_fit_font:
            effective_size = fit_size
        else:
            effective_size = max(config.fixed_font_size, 6)
        if not text_height_mm and abs(config.font_scale - 100.0) > 0.5:
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

        # 3b. Handle Barcode (Code 128): the bars keep their scannable width, Size sets their height
        barcode_img = None
        if config.barcode_enabled and config.barcode_data.strip():
            self._barcode_bad_chars = barcode.unsupported_chars(config.barcode_data.strip())
            barcode_img = self.generate_barcode_image(
                config.barcode_data, inner_h, config.barcode_scale, config.barcode_show_text, config.font_name
            )

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

        if barcode_img:
            if config.barcode_position == "right":
                elements_right.append(barcode_img)
            else:
                elements_left.append(barcode_img)

        if merged_img:
            if config.image_position == "left":
                elements_left.append(merged_img)
            elif config.image_position == "right":
                elements_right.append(merged_img)

        # One gap between neighbours, none after the last, so a code or picture on its own sits
        # in the middle of the label
        elements = elements_left + elements_right
        for el in elements:
            total_content_w += el.width
        total_content_w += gap * max(len(elements) + (1 if has_text else 0) - 1, 0)

        if has_text:
            total_content_w += text_w
        elif not elements_left and not elements_right:
            total_content_w += 20

        total_content_w += config.end_margin

        # A set length is exact: a shorter one cuts off the end of the content, as the user chose
        cut_dots = 0
        if config.fixed_width_mm:
            target_dots = int(round(config.fixed_width_mm / self.DOT_PITCH_MM))
            # The blank tape either side up to the cut lines is part of the label's length
            if config.cut_line:
                target_dots -= 2 * (BATCH_GAP_DOTS // 2)
            target_dots = max(target_dots, 10)
            cut_dots = max(total_content_w - target_dots, 0)
            self._cut_off_mm = cut_dots * self.DOT_PITCH_MM
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

        # What runs past the end stops where the side padding and frame begin
        if cut_dots:
            edge = img_canvas.width - config.end_margin - config.h_padding - frame_inset_x
            draw.rectangle([max(edge, 0), 0, img_canvas.width, canvas_h], fill="white")

        self._draw_border(img_canvas, border, config, print_border, printable_h)

        return img_canvas, spec, print_border, printable_h, canvas_h, effective_size

    def _draw_border(self, canvas: Image.Image, border, config: LabelConfig, print_border: int, printable_h: int):
        """Draws the label's border round the printable band, inside the side padding."""
        if border.id == "none":
            return
        width = canvas.width - 2 * config.h_padding - config.end_margin
        if width < 4:
            return
        # Borders are designed for the 180 dpi head; a finer head draws them at the same size
        scale = (25.4 / 180) / self.DOT_PITCH_MM
        mask = borders.render(border.id, width, printable_h, scale)
        canvas.paste("black", (config.h_padding, print_border), mask)

    def _vertical_block(self, doc, layout, size: int) -> Image.Image:
        """
        Every line of the text as a column of upright letters, the first line on the left, as
        the label reads when the tape is stuck on upright. Returns the block as it reads then.
        """
        cells = []
        for line in doc.lines:
            column = []
            for run in line.runs:
                for ch in run.text:
                    single = rich_text.Line(runs=[dataclasses.replace(run, text=ch)], size=line.size)
                    column.append(layout.render_line(single, size) if ch.strip() else None)
            cells.append(column)
        cap = max(layout.cap_height(size), 1)
        step = int(round(cap * 1.3))
        col_w = max([img.width for col in cells for img in col if img is not None] + [cap])
        col_gap = max(2, int(round(cap * 0.25)))
        rows = max([len(col) for col in cells] + [1])
        width = len(cells) * col_w + (len(cells) - 1) * col_gap
        out = Image.new("L", (max(width, 1), max(rows * step, 1)), 0)
        for c, column in enumerate(cells):
            x0 = c * (col_w + col_gap)
            for r, img in enumerate(column):
                if img is None:
                    continue
                box = img.getbbox()
                if not box:
                    continue
                ink = img.crop(box)
                # Each letter sits in the middle of its cell, so round and tall letters line up
                out.paste(ink, (x0 + (col_w - ink.width) // 2, r * step + (step - ink.height) // 2))
        return out

    def _turned_block(self, doc, layout, size: int, vertical: bool) -> Image.Image:
        """The text block as the tape reads when stuck on upright (before turning it onto the tape)."""
        return self._vertical_block(doc, layout, size) if vertical else layout.render(size)

    def _render_turned_text(self, config, doc, layout, border, spec, print_border, printable_h, canvas_h):
        """
        A label for tape stuck on upright: the text block is drawn as it reads then and turned a
        quarter onto the tape, so its width runs across the tape. Codes and pictures are left
        out; the border goes round the text.
        """
        vertical = config.direction == "vertical"
        inset_x, inset_y = border.insets(printable_h)
        across = printable_h - 2 * inset_y  # the room across the tape, for the block's width

        def width_at(size):
            return self._turned_block(doc, layout, size, vertical).width

        # Fit: the largest size whose block is as wide as the tape allows
        low, high, fit = 6, max(printable_h * 2, 6), 6
        while low <= high:
            mid = (low + high) // 2
            if width_at(mid) <= across:
                fit, low = mid, mid + 1
            else:
                high = mid - 1
        self._max_text_height_mm = layout.cap_height(fit) * self.DOT_PITCH_MM
        size = fit
        if config.text_height_mm:
            wanted = layout.size_for_cap_height(config.text_height_mm / self.DOT_PITCH_MM)
            if wanted <= fit or not config.text_height_fallback:
                size = wanted
            else:
                self._text_height_fell_back = True
        elif not config.auto_fit_font:
            size = max(config.fixed_font_size, 6)
        if not config.text_height_mm and abs(config.font_scale - 100.0) > 0.5:
            size = max(int(round(size * (config.font_scale / 100.0))), 6)

        block = self._turned_block(doc, layout, size, vertical)
        self._last_text_overflow = block.width > across
        # A quarter turn to the left: the top of the upright label is the start of the tape
        text_img = block.rotate(90, expand=True)

        length = text_img.width + 2 * (config.h_padding + inset_x) + config.end_margin
        cut_dots = 0
        if config.fixed_width_mm:
            target = int(round(config.fixed_width_mm / self.DOT_PITCH_MM))
            if config.cut_line:
                target -= 2 * (BATCH_GAP_DOTS // 2)
            target = max(target, 10)
            cut_dots = max(length - target, 0)
            self._cut_off_mm = cut_dots * self.DOT_PITCH_MM
            length = target
        canvas = Image.new("RGB", (max(length, 10), canvas_h), "white")
        if config.fixed_width_mm and not cut_dots:
            x = (length - config.end_margin - text_img.width) // 2
        else:
            x = config.h_padding + inset_x
        y = print_border + (printable_h - text_img.height) // 2 + config.v_shift
        canvas.paste("black", (x, y), text_img)
        if cut_dots:
            edge = canvas.width - config.end_margin - config.h_padding - inset_x
            ImageDraw.Draw(canvas).rectangle([max(edge, 0), 0, canvas.width, canvas_h], fill="white")
        self._draw_border(canvas, border, config, print_border, printable_h)
        return canvas, spec, print_border, printable_h, canvas_h, size

    def _single_pad(self, config: LabelConfig) -> int:
        """
        Blank dots on each side of a label printed on its own. A label gets the same half-gap
        of tape as a label in a batch, so single and queued prints look alike. Bin labels are
        drawn border to border, so without cut lines they still get a little blank tape on
        each side.
        """
        if config.cut_line:
            return BATCH_GAP_DOTS // 2
        if getattr(config, "inventory_config", None) is not None:
            return int(round(SINGLE_BIN_PADDING_MM / self.DOT_PITCH_MM))
        return 0

    def tape_lengths(self, configs: List[LabelConfig], gap_dots: int = BATCH_GAP_DOTS) -> dict:
        """
        What it takes to work out the tape any run of these labels uses, without drawing the
        strips: each label's width in dots in a batch and on its own, the gap between batched
        labels and the blank tape at a batch's two ends. A run of n >= 2 labels prints
        sum(widths) + gap * (n - 1) + ends dots, one label prints its single width, and every
        print adds the lead of tape before it (all as render_batch and render count them).
        """
        widths, singles = [], []
        for cfg in configs:
            canvas = self._render_base_canvas(cfg)[0]
            widths.append(canvas.width)
            singles.append(canvas.width + 2 * self._single_pad(cfg))
        return {
            "widths": widths,
            "singles": singles,
            "gap": gap_dots,
            "ends": 2 * (gap_dots // 2),
            "dot_mm": self.DOT_PITCH_MM,
            "lead_mm": TAPE_LEAD_MM,
            "max_mm": self.MAX_TOTAL_LENGTH_MM,
        }

    def port_texts(self, config: LabelConfig) -> List[str]:
        """What goes over each port of a port strip: its name, or the prefix and its number."""
        count = max(1, int(config.port_count))
        if config.port_use_names:
            names = (config.port_names or "").split("\n")
            return [(names[i].strip() if i < len(names) else "") for i in range(count)]
        first = int(config.port_first)
        return [f"{config.port_prefix.strip()}{first + i}" for i in range(count)]

    def _render_port_strip(
        self, config: LabelConfig, spec: dict, print_border: int, printable_h: int, canvas_h: int
    ) -> Tuple[Image.Image, dict, int, int, int, int]:
        """
        A strip with one cell per port, port_pitch_mm wide. Each cell edge is rounded to the
        nearest dot from the start of the strip, so the error never adds up along it: every
        port is within half a dot (0.07 mm) of where it should be.
        """
        count = max(1, int(config.port_count))
        pitch = max(float(config.port_pitch_mm), 3.0) / self.DOT_PITCH_MM
        edges = [int(round(i * pitch)) for i in range(count + 1)]
        img_canvas = Image.new("RGB", (edges[-1], canvas_h), "white")
        draw = ImageDraw.Draw(img_canvas)

        every = int(config.port_divider_every or 0)
        for i in range(1, count):
            width = PORT_THICK_DIVIDER_DOTS if every > 0 and i % every == 0 else PORT_DIVIDER_DOTS
            left = edges[i] - width // 2
            draw.rectangle([left, print_border, left + width - 1, print_border + printable_h - 1], fill="black")

        texts = self.port_texts(config)
        layouts = {
            t: rich_text.TextLayout(rich_text.parse(t), config.font_name, config.stroke_width, 1.0, "center")
            for t in texts if t
        }
        room_w = min(b - a for a, b in zip(edges, edges[1:])) - PORT_THICK_DIVIDER_DOTS - 2 * PORT_TEXT_MARGIN_DOTS
        room_w = max(room_w, 4)
        room_h = printable_h - 2 * PORT_TEXT_V_MARGIN_DOTS

        def widest(size: int) -> int:
            return max(layout.render(size).width for layout in layouts.values())

        def fit_width(size: int) -> int:
            # Text width grows about in step with the size, so one guess and a few steps down
            w = widest(size)
            if w > room_w:
                size = max(int(size * room_w / w), 4)
                while size > 4 and widest(size) > room_w:
                    size -= 1
            return size

        size = 0
        if layouts:
            probe = next(iter(layouts.values()))
            fit = fit_width(min(layout.fit_size(room_h) for layout in layouts.values()))
            self._max_text_height_mm = probe.cap_height(fit) * self.DOT_PITCH_MM
            size = fit
            if config.text_height_mm:
                wanted = probe.size_for_cap_height(config.text_height_mm / self.DOT_PITCH_MM)
                if config.text_height_fallback and wanted > fit:
                    self._text_height_fell_back = True
                else:
                    size = wanted
                    self._last_text_overflow = any(l.height(size) > printable_h for l in layouts.values())

            # Every port's text sits on the same line, with its capital letters centred on the tape
            cap = probe.cap_height(size)
            for i, text in enumerate(texts):
                if not text:
                    continue
                layout = layouts[text]
                line = layout.doc.lines[0]
                top, _ = layout._line_box(line, size)
                mask = layout.render_line(line, size)
                x = (edges[i] + edges[i + 1] - mask.width) // 2
                y = print_border + (printable_h - cap) // 2 - (-top - cap) + config.v_shift
                img_canvas.paste("black", (x, y), mask)

        return img_canvas, spec, print_border, printable_h, canvas_h, size

    def _render_cable_flag(self, config: LabelConfig) -> Tuple[Image.Image, dict, int, int, int, int]:
        """The label drawn twice, with a blank stretch between that goes once round the cable."""
        side_config = dataclasses.replace(
            config, layout="text", fixed_width_mm=config.flag_side_mm, cut_line=False
        )
        side, spec, print_border, printable_h, canvas_h, size = self._render_base_canvas(side_config)
        wrap = max(int(round(math.pi * max(float(config.flag_cable_mm), 1.0) / self.DOT_PITCH_MM)), 1)
        img_canvas = Image.new("RGB", (2 * side.width + wrap, canvas_h), "white")
        img_canvas.paste(side, (0, 0))
        img_canvas.paste(side, (side.width + wrap, 0))
        if config.flag_fold_marks:
            draw = ImageDraw.Draw(img_canvas)
            bottom = print_border + printable_h - 1
            for x in (side.width, side.width + wrap - 1):
                draw.line([(x, print_border), (x, print_border + FLAG_MARK_DOTS - 1)], fill="black")
                draw.line([(x, bottom - FLAG_MARK_DOTS + 1), (x, bottom)], fill="black")
        return img_canvas, spec, print_border, printable_h, canvas_h, size

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

        pad = self._single_pad(config)
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
                draw_cut_line(draw, cx, print_border, printable_h, config.cut_line_style)

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
        elif self._cut_off_mm >= 0.5:
            warning = (f"The content needs {self._cut_off_at_mm + self._cut_off_mm:.0f} mm, so the end is cut off "
                       f"at {self._cut_off_at_mm:g} mm.")
        elif getattr(self, "_barcode_bad_chars", ""):
            warning = (f"A barcode can't hold {self._barcode_bad_chars}. Use plain letters, numbers "
                       "and symbols.")
        elif getattr(self, "_last_text_overflow", False) and config.text_height_mm and not self._text_height_fell_back:
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
            max_text_height_mm=None if self._max_text_height_mm is None else round(self._max_text_height_mm, 2),
            text_height_fell_back=self._text_height_fell_back,
        )

        return preview_img, padded_128, raster_bytes, metrics

    def render_batch(
        self, configs: List[LabelConfig], gap_dots: int = BATCH_GAP_DOTS,
        spans: Optional[List[Tuple[int, int]]] = None,
    ) -> Tuple[Image.Image, Image.Image, bytes, LabelMetrics]:
        """
        Renders a continuous batch chain of multiple labels with cut lines in between,
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
            draw_cut_line(draw, x, print_border, printable_h, configs[0].cut_line_style)

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
