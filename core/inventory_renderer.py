#!/usr/bin/env python3
"""
Hardware Inventory Label Design System & Template Catalog (V2) Engine.
Implements crisp procedural vector rendering for modular storage bin labels:
- Archetype A: Threaded Fasteners (Screws, Nuts, Washers)
- Archetype B: Discrete Components & Electrical Hardware
Adheres to V2 standards: 1-bit thermal output, inverted high-contrast anchor blocks,
strict 8-10% interior safe zones, and 2-3px architectural divider hairlines.
"""

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Union
from PIL import Image, ImageDraw, ImageFont, ImageOps

from core.font_manager import font_manager


@dataclass
class FastenerLabelConfig:
    """Configuration for Archetype A: Threaded Fasteners."""
    thread_size: str = "M3"              # e.g. "M3", "M4", "M5", "M6", "M8", "M10"
    category: str = "SKRUV"               # e.g. "SKRUV", "MUTTER", "BRICKOR"
    compartment_mode: str = "dual"        # "single", "dual", "quad", "assortment"
    
    # Single size fields
    length_single: str = "x 20"
    standard_line1: str = "DIN 933"       # optional standard e.g. "DIN 933"
    standard_line2: str = "FZB • 8.8"     # optional grade/coating
    
    # Dual compartment (2 lengths)
    length_dual_1: str = "x30"
    length_dual_2: str = "x35"
    
    # Quad compartment (2x2 grid)
    length_quad_1: str = "x25"
    length_quad_2: str = "x18"
    length_quad_3: str = "x20"
    length_quad_4: str = "x16"
    
    # Assortment / Custom text
    assortment_line1: str = "Blandade"
    assortment_line2: str = "sorter"
    
    # Tool Drive Badge
    tool_type: str = "internal_hex"       # "internal_hex", "external_hex", "washer", "torx", "phillips", "none"
    tool_size: str = "2.5"                # e.g. "2.5", "3", "4", "8", "10", "17"
    
    # Dimensions
    label_width_mm: float = 38.0          # Typical width for organizer bin (38mm ~ 255 dots)
    tape_width_mm: int = 12


@dataclass
class ComponentLabelConfig:
    """Configuration for Archetype B: Discrete Components & Electrical Hardware."""
    category_banner: str = "KULLAGER"     # e.g. "KULLAGER", "WAGO", "SÄKRINGSHÅLLARE"
    spec_primary: str = "608ZZ"           # e.g. "608ZZ", "221-413 • 3-väg", "16 AWG / 1.3 mm²"
    spec_secondary: str = ""              # e.g. "0.2 - 4.0 mm²", "Inline Type"
    icon_type: str = "ball_bearing"       # "ball_bearing", "wago", "fuse", "resistor", "capacitor", "none"
    
    # Dimensions
    label_width_mm: float = 38.0          # Typical width for organizer bin (38mm ~ 255 dots)
    tape_width_mm: int = 12


class InventoryRenderer:
    """
    Renders high-contrast V2 inventory labels with vector precision.
    Outputs 1-bit base canvas (64 dots height for 12mm tape) ready for thermal printing.
    """

    DOT_PITCH_MM = 0.149  # ~180 DPI
    PRINTABLE_HEIGHT = 64  # dots for 12mm tape
    SUPERSAMPLE = 4        # 4x internal rendering for crisp geometric vector drawing

    def __init__(self):
        pass

    # =========================================================================
    # VECTOR ICON DRAWING HELPERS (Internal 4x scale coordinates)
    # =========================================================================

    @staticmethod
    def _draw_internal_hex(draw: ImageDraw.ImageDraw, cx: float, cy: float, radius: float, fill=0):
        """Solid filled hexagon (Socket cap / Allen key)."""
        pts = [
            (
                cx + radius * math.cos(math.radians(60 * i + 30)),
                cy + radius * math.sin(math.radians(60 * i + 30)),
            )
            for i in range(6)
        ]
        draw.polygon(pts, fill=fill)

    @staticmethod
    def _draw_external_hex(draw: ImageDraw.ImageDraw, cx: float, cy: float, radius: float, stroke: int, outline=0):
        """Outlined hexagon with hollow center (Hex nut / external bolt wrench)."""
        pts = [
            (
                cx + radius * math.cos(math.radians(60 * i + 30)),
                cy + radius * math.sin(math.radians(60 * i + 30)),
            )
            for i in range(6)
        ]
        draw.polygon(pts, outline=outline, width=stroke)

    @staticmethod
    def _draw_washer_icon(draw: ImageDraw.ImageDraw, cx: float, cy: float, outer_r: float, stroke: int, outline=0, fill=0):
        """Concentric circles donut profile (Washer)."""
        draw.ellipse([(cx - outer_r, cy - outer_r), (cx + outer_r, cy + outer_r)], outline=outline, width=stroke)
        inner_r = outer_r * 0.42
        draw.ellipse([(cx - inner_r, cy - inner_r), (cx + inner_r, cy + inner_r)], fill=fill)

    @staticmethod
    def _draw_torx_icon(draw: ImageDraw.ImageDraw, cx: float, cy: float, r: float, fill=0):
        """6-pointed star / Torx drive silhouette."""
        pts = []
        r_inner = r * 0.55
        for i in range(12):
            rad = r if (i % 2 == 0) else r_inner
            angle = math.radians(30 * i)
            pts.append((cx + rad * math.cos(angle), cy + rad * math.sin(angle)))
        draw.polygon(pts, fill=fill)

    @staticmethod
    def _draw_phillips_icon(draw: ImageDraw.ImageDraw, cx: float, cy: float, r: float, stroke: int, fill=0):
        """Cross / Phillips drive silhouette."""
        w = r * 0.35
        draw.rectangle([(cx - w, cy - r), (cx + w, cy + r)], fill=fill)
        draw.rectangle([(cx - r, cy - w), (cx + r, cy + w)], fill=fill)

    @staticmethod
    def _draw_ball_bearing_icon(draw: ImageDraw.ImageDraw, cx: float, cy: float, r: float, stroke: int):
        """Concentric ball bearing with internal rolling elements."""
        draw.ellipse([(cx - r, cy - r), (cx + r, cy + r)], outline=0, width=stroke)
        inner_r = r * 0.42
        draw.ellipse([(cx - inner_r, cy - inner_r), (cx + inner_r, cy + inner_r)], outline=0, width=stroke)
        # 6 balls
        ball_dist = (r + inner_r) / 2
        ball_r = (r - inner_r) / 4.2
        for i in range(6):
            ang = math.radians(60 * i)
            bx = cx + ball_dist * math.cos(ang)
            by = cy + ball_dist * math.sin(ang)
            draw.ellipse([(bx - ball_r, by - ball_r), (bx + ball_r, by + ball_r)], fill=0)

    @staticmethod
    def _draw_wago_icon(draw: ImageDraw.ImageDraw, cx: float, cy: float, r: float, stroke: int):
        """Line-art depiction of WAGO lever wire splice connector."""
        box_w = r * 1.5
        box_h = r * 1.2
        bx0 = cx - box_w / 2
        by0 = cy - box_h / 2
        # Body
        draw.rectangle([(bx0, by0), (bx0 + box_w, by0 + box_h)], outline=0, width=stroke)
        # Port dividers (3 ports)
        p_w = box_w / 3.0
        draw.line([(bx0 + p_w, by0 + box_h * 0.45), (bx0 + p_w, by0 + box_h)], fill=0, width=stroke)
        draw.line([(bx0 + 2 * p_w, by0 + box_h * 0.45), (bx0 + 2 * p_w, by0 + box_h)], fill=0, width=stroke)
        # Lever lines (raised levers)
        for k in range(3):
            lx = bx0 + (k + 0.5) * p_w
            draw.line([(lx, by0 + box_h * 0.45), (lx, by0 + 2)], fill=0, width=stroke + 1)

    @staticmethod
    def _draw_fuse_icon(draw: ImageDraw.ImageDraw, cx: float, cy: float, r: float, stroke: int):
        """Inline cylindrical cartridge fuse icon."""
        cyl_w = r * 1.6
        cyl_h = r * 0.65
        cx0 = cx - cyl_w / 2
        cy0 = cy - cyl_h / 2
        # Center glass
        draw.rectangle([(cx0, cy0), (cx0 + cyl_w, cy0 + cyl_h)], outline=0, width=stroke)
        # Metal end caps
        cap_w = cyl_w * 0.25
        draw.rectangle([(cx0, cy0), (cx0 + cap_w, cy0 + cyl_h)], fill=0)
        draw.rectangle([(cx0 + cyl_w - cap_w, cy0), (cx0 + cyl_w, cy0 + cyl_h)], fill=0)
        # Filament line through center
        draw.line([(cx0 - r * 0.3, cy), (cx0 + cyl_w + r * 0.3, cy)], fill=0, width=stroke)

    # =========================================================================
    # ARCHETYPE A: THREADED FASTENERS
    # =========================================================================

    def render_fastener(self, cfg: FastenerLabelConfig) -> Image.Image:
        """
        Renders Archetype A (Threaded Fastener).
        Returns a high-contrast 1-bit PIL Image of height 64 dots.
        """
        scale = self.SUPERSAMPLE
        target_h = self.PRINTABLE_HEIGHT
        target_w = max(int(round(cfg.label_width_mm / self.DOT_PITCH_MM)), 120)

        canvas_w = target_w * scale
        canvas_h = target_h * scale

        # High-resolution work canvas (white background)
        img = Image.new("L", (canvas_w, canvas_h), 255)
        draw = ImageDraw.Draw(img)

        # Hairline divider stroke (2-3px equivalent at 64 dots -> 8px at 4x)
        line_w = int(2.0 * scale)

        # 1. Outer Bounding Border
        draw.rectangle([(0, 0), (canvas_w - 1, canvas_h - 1)], outline=0, width=line_w)

        # 2. Left Inverted Anchor Block (32% width)
        anchor_w = int(canvas_w * 0.32)
        draw.rectangle([(0, 0), (anchor_w, canvas_h - 1)], fill=0)

        # Anchor text (e.g. M3, M5, M10)
        thread_txt = cfg.thread_size.strip()
        f_size = 52 * scale if len(thread_txt) <= 2 else (42 * scale if len(thread_txt) <= 3 else 32 * scale)
        font_anchor = font_manager.load_font("Arial Bold", f_size)
        draw.text((anchor_w // 2, canvas_h // 2), thread_txt, font=font_anchor, fill=255, anchor="mm")

        # 3. Top Category Header Bar (Top 36% of remaining area)
        rem_w = canvas_w - anchor_w
        header_h = int(canvas_h * 0.36)
        draw.line([(anchor_w, header_h), (canvas_w - 1, header_h)], fill=0, width=line_w)

        cat_txt = cfg.category.strip().upper()
        font_cat = font_manager.load_font("Arial Bold", 22 * scale)
        draw.text(
            (anchor_w + rem_w // 2, header_h // 2),
            cat_txt,
            font=font_cat,
            fill=0,
            anchor="mm",
        )

        # 4. Bottom Area: Compartments & Tool Drive
        bot_y0 = header_h
        bot_h = canvas_h - header_h

        # Determine Tool Drive Slot width
        has_tool = cfg.tool_type != "none"
        tool_slot_w = int(rem_w * 0.32) if has_tool else 0
        comp_w = rem_w - tool_slot_w

        # Vertical divider before tool slot
        if has_tool:
            tool_x = anchor_w + comp_w
            draw.line([(tool_x, bot_y0), (tool_x, canvas_h - 1)], fill=0, width=line_w)

            # Draw Tool Badge (Tool size text + vector icon)
            self._render_tool_badge(
                draw,
                tool_x,
                bot_y0,
                tool_slot_w,
                bot_h,
                cfg.tool_type,
                cfg.tool_size,
                scale,
                line_w,
            )

        # 5. Render Compartment Matrix inside comp_w
        comp_x0 = anchor_w
        mode = cfg.compartment_mode.lower()

        if mode == "single":
            self._render_fastener_single(draw, comp_x0, bot_y0, comp_w, bot_h, cfg, scale)
        elif mode == "dual":
            self._render_fastener_dual(draw, comp_x0, bot_y0, comp_w, bot_h, cfg, scale, line_w)
        elif mode == "quad":
            self._render_fastener_quad(draw, comp_x0, bot_y0, comp_w, bot_h, cfg, scale, line_w)
        elif mode == "assortment":
            self._render_fastener_assortment(draw, comp_x0, bot_y0, comp_w, bot_h, cfg, scale)
        else:
            self._render_fastener_dual(draw, comp_x0, bot_y0, comp_w, bot_h, cfg, scale, line_w)

        # Downsample to target 64 dots height with high-quality threshold
        downsampled = img.resize((target_w, target_h), Image.Resampling.LANCZOS)
        bin_img = downsampled.point(lambda p: 255 if p > 128 else 0).convert("1")
        return bin_img

    def _render_fastener_single(
        self, draw: ImageDraw.ImageDraw, x0: int, y0: int, w: int, h: int, cfg: FastenerLabelConfig, scale: int
    ):
        has_std = bool(cfg.standard_line1.strip())
        if has_std:
            f_len = font_manager.load_font("Arial Bold", 24 * scale)
            draw.text((x0 + w * 0.45, y0 + h * 0.35), cfg.length_single, font=f_len, fill=0, anchor="mm")
            f_sub = font_manager.load_font("Arial Bold", 12 * scale)
            draw.text((x0 + w * 0.45, y0 + h * 0.75), f"{cfg.standard_line1} {cfg.standard_line2}".strip(), font=f_sub, fill=0, anchor="mm")
        else:
            f_len = font_manager.load_font("Arial Bold", 28 * scale)
            draw.text((x0 + w // 2, y0 + h // 2), cfg.length_single, font=f_len, fill=0, anchor="mm")

    def _render_fastener_dual(
        self, draw: ImageDraw.ImageDraw, x0: int, y0: int, w: int, h: int, cfg: FastenerLabelConfig, scale: int, line_w: int
    ):
        f_len = font_manager.load_font("Arial Bold", 22 * scale)
        draw.text((x0 + w * 0.28, y0 + h // 2), cfg.length_dual_1, font=f_len, fill=0, anchor="mm")
        draw.text((x0 + w * 0.72, y0 + h // 2), cfg.length_dual_2, font=f_len, fill=0, anchor="mm")

    def _render_fastener_quad(
        self, draw: ImageDraw.ImageDraw, x0: int, y0: int, w: int, h: int, cfg: FastenerLabelConfig, scale: int, line_w: int
    ):
        f_grid = font_manager.load_font("Arial Bold", 15 * scale)
        draw.text((x0 + w * 0.28, y0 + h * 0.28), cfg.length_quad_1, font=f_grid, fill=0, anchor="mm")
        draw.text((x0 + w * 0.72, y0 + h * 0.28), cfg.length_quad_2, font=f_grid, fill=0, anchor="mm")
        draw.text((x0 + w * 0.28, y0 + h * 0.72), cfg.length_quad_3, font=f_grid, fill=0, anchor="mm")
        draw.text((x0 + w * 0.72, y0 + h * 0.72), cfg.length_quad_4, font=f_grid, fill=0, anchor="mm")

    def _render_fastener_assortment(
        self, draw: ImageDraw.ImageDraw, x0: int, y0: int, w: int, h: int, cfg: FastenerLabelConfig, scale: int
    ):
        f_assort = font_manager.load_font("Arial Bold", 14 * scale)
        draw.text((x0 + w // 2, y0 + h * 0.30), cfg.assortment_line1, font=f_assort, fill=0, anchor="mm")
        draw.text((x0 + w // 2, y0 + h * 0.70), cfg.assortment_line2, font=f_assort, fill=0, anchor="mm")

    def _render_tool_badge(
        self,
        draw: ImageDraw.ImageDraw,
        x0: int,
        y0: int,
        w: int,
        h: int,
        tool_type: str,
        tool_size: str,
        scale: int,
        line_w: int,
    ):
        has_size_txt = bool(tool_size.strip())
        mid_y = y0 + h // 2

        if has_size_txt and tool_type != "washer":
            f_size = font_manager.load_font("Arial Bold", 18 * scale)
            draw.text((x0 + w * 0.35, mid_y), tool_size.strip(), font=f_size, fill=0, anchor="mm")
            icon_cx = x0 + w * 0.75
        else:
            icon_cx = x0 + w // 2

        icon_r = 11 * scale

        if tool_type == "internal_hex":
            self._draw_internal_hex(draw, icon_cx, mid_y, icon_r, fill=0)
        elif tool_type == "external_hex":
            self._draw_external_hex(draw, icon_cx, mid_y, icon_r, stroke=line_w, outline=0)
        elif tool_type == "washer":
            self._draw_washer_icon(draw, icon_cx, mid_y, icon_r * 1.05, stroke=line_w, outline=0, fill=0)
        elif tool_type == "torx":
            self._draw_torx_icon(draw, icon_cx, mid_y, icon_r, fill=0)
        elif tool_type == "phillips":
            self._draw_phillips_icon(draw, icon_cx, mid_y, icon_r, stroke=line_w, fill=0)

    # =========================================================================
    # ARCHETYPE B: DISCRETE COMPONENTS & ELECTRICAL HARDWARE
    # =========================================================================

    def render_component(self, cfg: ComponentLabelConfig) -> Image.Image:
        """
        Renders Archetype B (Discrete Components & Electrical Modules).
        Returns a high-contrast 1-bit PIL Image of height 64 dots.
        """
        scale = self.SUPERSAMPLE
        target_h = self.PRINTABLE_HEIGHT
        target_w = max(int(round(cfg.label_width_mm / self.DOT_PITCH_MM)), 120)

        canvas_w = target_w * scale
        canvas_h = target_h * scale

        img = Image.new("L", (canvas_w, canvas_h), 255)
        draw = ImageDraw.Draw(img)
        line_w = int(2.0 * scale)

        # 1. Outer Border
        draw.rectangle([(0, 0), (canvas_w - 1, canvas_h - 1)], outline=0, width=line_w)

        # 2. Right Icon Frame (Square slot based on height)
        has_icon = cfg.icon_type != "none"
        icon_w = int(canvas_h) if has_icon else 0
        left_content_w = canvas_w - icon_w

        if has_icon:
            icon_x0 = canvas_w - icon_w
            draw.line([(icon_x0, 0), (icon_x0, canvas_h - 1)], fill=0, width=line_w)

            icon_cx = icon_x0 + icon_w // 2
            icon_cy = canvas_h // 2
            icon_r = 17 * scale

            if cfg.icon_type == "ball_bearing":
                self._draw_ball_bearing_icon(draw, icon_cx, icon_cy, icon_r, stroke=line_w)
            elif cfg.icon_type == "wago":
                self._draw_wago_icon(draw, icon_cx, icon_cy, icon_r, stroke=line_w)
            elif cfg.icon_type == "fuse":
                self._draw_fuse_icon(draw, icon_cx, icon_cy, icon_r, stroke=line_w)

        # 3. Top Category Banner Strip (36% height) with Solid Inverted Block
        banner_h = int(canvas_h * 0.36)
        draw.rectangle([(0, 0), (left_content_w, banner_h)], fill=0)

        cat_txt = cfg.category_banner.strip().upper()
        font_banner = font_manager.load_font("Arial Bold", 22 * scale)
        draw.text(
            (left_content_w // 2, banner_h // 2),
            cat_txt,
            font=font_banner,
            fill=255,
            anchor="mm",
        )

        # 4. Lower Spec Area (64% height)
        bot_y0 = banner_h
        bot_h = canvas_h - banner_h
        has_sec = bool(cfg.spec_secondary.strip())

        if has_sec:
            f_pri = font_manager.load_font("Arial Bold", 21 * scale)
            draw.text((left_content_w // 2, bot_y0 + bot_h * 0.35), cfg.spec_primary, font=f_pri, fill=0, anchor="mm")
            f_sec = font_manager.load_font("Arial Bold", 13 * scale)
            draw.text((left_content_w // 2, bot_y0 + bot_h * 0.75), cfg.spec_secondary, font=f_sec, fill=0, anchor="mm")
        else:
            f_pri = font_manager.load_font("Arial Bold", 28 * scale)
            draw.text((left_content_w // 2, bot_y0 + bot_h // 2), cfg.spec_primary, font=f_pri, fill=0, anchor="mm")

        # Downsample to target 64 dots height
        downsampled = img.resize((target_w, target_h), Image.Resampling.LANCZOS)
        bin_img = downsampled.point(lambda p: 255 if p > 128 else 0).convert("1")
        return bin_img


inventory_renderer = InventoryRenderer()


INVENTORY_PRESETS = {
    "A1: Hex Head Screw (M5 x 20, DIN 933)": FastenerLabelConfig(
        thread_size="M5",
        category="SKRUV",
        compartment_mode="single",
        length_single="x 20",
        standard_line1="DIN 933",
        standard_line2="FZB • 8.8",
        tool_type="external_hex",
        tool_size="8",
    ),
    "A2: Socket Cap 2-Bin (M3 x30 x35)": FastenerLabelConfig(
        thread_size="M3",
        category="SKRUV",
        compartment_mode="dual",
        length_dual_1="x30",
        length_dual_2="x35",
        tool_type="internal_hex",
        tool_size="2.5",
    ),
    "A3: Socket Cap 4-Bin (M3 2×2 Grid)": FastenerLabelConfig(
        thread_size="M3",
        category="SKRUV",
        compartment_mode="quad",
        length_quad_1="x25",
        length_quad_2="x18",
        length_quad_3="x20",
        length_quad_4="x16",
        tool_type="internal_hex",
        tool_size="2.5",
    ),
    "A4: Hex Nut Assortment (M5 MUTTER)": FastenerLabelConfig(
        thread_size="M5",
        category="MUTTER",
        compartment_mode="assortment",
        assortment_line1="Blandade",
        assortment_line2="sorter",
        tool_type="external_hex",
        tool_size="8",
    ),
    "A5: Washer Assortment (M5 BRICKOR)": FastenerLabelConfig(
        thread_size="M5",
        category="BRICKOR",
        compartment_mode="assortment",
        assortment_line1="Blandade",
        assortment_line2="storlekar",
        tool_type="washer",
        tool_size="",
    ),
    "B1: Ball Bearings (KULLAGER 608ZZ)": ComponentLabelConfig(
        category_banner="KULLAGER",
        spec_primary="608ZZ",
        spec_secondary="",
        icon_type="ball_bearing",
    ),
    "B2: Lever Connectors (WAGO 221-413)": ComponentLabelConfig(
        category_banner="WAGO",
        spec_primary="221-413 • 3-väg",
        spec_secondary="0.2 – 4.0 mm²",
        icon_type="wago",
    ),
    "B3: Inline Fuse Holder (16 AWG)": ComponentLabelConfig(
        category_banner="SÄKRINGSHÅLLARE",
        spec_primary="16 AWG / 1.3 mm²",
        spec_secondary="Inline Type",
        icon_type="fuse",
    ),
}
