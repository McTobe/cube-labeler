#!/usr/bin/env python3
"""
Unit tests for Hardware Inventory Label Design System & Template Catalog (V2).
"""

import os
import sys
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from core.inventory_renderer import (
    InventoryRenderer,
    FastenerLabelConfig,
    ComponentLabelConfig,
    inventory_renderer,
)
from core.label_renderer import SINGLE_BIN_PADDING_MM, LabelConfig, LabelRenderer
from core.specs import DOT_PITCH_MM
from core.label_language import build_presets

INVENTORY_PRESETS = {pid: p.config for pid, p in build_presets("en").items()}


class TestInventoryRenderer(unittest.TestCase):
    """Test suite for V2 procedural inventory label generation."""

    def setUp(self):
        self.renderer = InventoryRenderer()
        self.label_renderer = LabelRenderer()

    def test_all_catalog_presets_render_successfully(self):
        """Verify all 8 V2 catalog templates produce valid 64-dot 1-bit images."""
        for name, preset in INVENTORY_PRESETS.items():
            if isinstance(preset, FastenerLabelConfig):
                img = self.renderer.render_fastener(preset)
            else:
                img = self.renderer.render_component(preset)

            self.assertEqual(img.size[1], 64, f"Height must be 64 dots for {name}")
            self.assertEqual(img.mode, "1", f"Mode must be 1-bit for {name}")
            # Ensure not blank (both black and white pixels exist)
            colors = img.getcolors()
            self.assertEqual(len(colors), 2, f"Template {name} should contain black and white pixels")

    def test_fastener_compartment_modes(self):
        """Verify Archetype A renders across all 4 compartment variations."""
        modes = ["single", "dual", "quad", "assortment"]
        for mode in modes:
            cfg = FastenerLabelConfig(
                thread_size="M4",
                category="SKRUV",
                compartment_mode=mode,
            )
            img = self.renderer.render_fastener(cfg)
            self.assertEqual(img.size[1], 64)
            self.assertEqual(img.mode, "1")

    def test_fastener_tool_types(self):
        """Verify all vector tool drive icons render cleanly without error."""
        tools = ["internal_hex", "external_hex", "washer", "torx", "phillips", "none"]
        for tool in tools:
            cfg = FastenerLabelConfig(
                thread_size="M3",
                category="SKRUV",
                tool_type=tool,
                tool_size="2.5" if tool != "washer" else "",
            )
            img = self.renderer.render_fastener(cfg)
            self.assertEqual(img.size[1], 64)

    def test_horizontal_tool_badge_no_clipping(self):
        """Verify number on the left and icon on the right never clip and support 2 numbers + dot."""
        test_cases = [
            ("2.5", "internal_hex"),
            ("8", "external_hex"),
            ("10", "external_hex"),
            ("T25", "torx"),
            ("PH2", "phillips"),
        ]
        for size_str, tool_type in test_cases:
            cfg = FastenerLabelConfig(
                thread_size="M3",
                category="SKRUV",
                compartment_mode="dual",
                tool_type=tool_type,
                tool_size=size_str,
            )
            img = self.renderer.render_fastener(cfg)
            self.assertEqual(img.size[1], 64)
            self.assertEqual(img.mode, "1")
            
            # Verify badge area has valid pixel distribution
            w, h = img.size
            # Top boundary row 23-26 (just below category header divider)
            # Inspect badge region (rightmost 25%)
            badge_crop = img.crop((int(w * 0.75), 26, w - 2, h - 3))
            # Must have black pixels (number + icon)
            black_count = sum(1 for p in badge_crop.convert("L").tobytes() if p == 0)
            self.assertGreater(black_count, 30, f"Expected black pixels for {size_str} {tool_type}")

    def test_component_icon_types(self):
        """Verify Archetype B renders across all component icon types."""
        icons = ["ball_bearing", "wago", "fuse", "none"]
        for icon in icons:
            cfg = ComponentLabelConfig(
                category_banner="HARDWARE",
                spec_primary="TEST-123",
                spec_secondary="Subline",
                icon_type=icon,
            )
            img = self.renderer.render_component(cfg)
            self.assertEqual(img.size[1], 64)

    def test_label_renderer_integration(self):
        """Verify seamless integration with core LabelRenderer and batch queuing."""
        cfg_fastener = LabelConfig(inventory_config=INVENTORY_PRESETS["A2"])
        prev, rast, r_bytes, metrics = self.label_renderer.render(cfg_fastener)

        self.assertEqual(rast.size[0], 128)  # 128-dot Brother printhead width
        self.assertGreater(len(r_bytes), 1000)
        # 38 mm label plus the blank tape left on each side of a single bin label
        padding_mm = 2 * round(SINGLE_BIN_PADDING_MM / DOT_PITCH_MM) * DOT_PITCH_MM
        self.assertAlmostEqual(metrics.print_length_mm, 38.0 + padding_mm, delta=1.5)

        # Batch rendering
        cfg_comp = LabelConfig(inventory_config=INVENTORY_PRESETS["B1"])
        b_prev, b_rast, b_bytes, b_metrics = self.label_renderer.render_batch([cfg_fastener, cfg_comp])

        self.assertEqual(b_metrics.label_count, 2)
        self.assertEqual(b_metrics.tape_saved_mm, 25.0)  # Saved 1 blank lead-in cycle

    def test_auto_shrink_typography_long_banner(self):
        """Verify long category headers and banners dynamically shrink without error or clipping."""
        # Long Archetype B banner (e.g. SÄKRINGSHÅLLARE)
        cfg_b = ComponentLabelConfig(
            category_banner="SÄKRINGSHÅLLARE",
            spec_primary="608ZZ",
            spec_secondary="Inline Type",
            icon_type="fuse",
            label_width_mm=38.0,
        )
        img_b = self.renderer.render_component(cfg_b)
        self.assertEqual(img_b.size[1], 64)
        self.assertEqual(img_b.mode, "1")
        self.assertEqual(len(img_b.getcolors()), 2)

        # Long Archetype A category and anchor
        cfg_a = FastenerLabelConfig(
            thread_size="#6-32",
            category="SKRUV & MUTTER",
            compartment_mode="dual",
            tool_type="internal_hex",
            tool_size="7/64\"",
            label_width_mm=38.0,
        )
        img_a = self.renderer.render_fastener(cfg_a)
        self.assertEqual(img_a.size[1], 64)
        self.assertEqual(img_a.mode, "1")
        self.assertEqual(len(img_a.getcolors()), 2)

    def test_custom_tool_and_component_icons(self):
        """Verify custom tool and component images load, binarize, and composite cleanly."""
        import tempfile
        from PIL import Image, ImageDraw

        with tempfile.TemporaryDirectory() as tmp_dir:
            icon_path = os.path.join(tmp_dir, "custom_icon.png")
            test_img = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
            d = ImageDraw.Draw(test_img)
            d.rectangle([4, 4, 28, 28], fill=(0, 0, 0, 255))
            test_img.save(icon_path)

            # Fastener with custom tool icon
            cfg_a = FastenerLabelConfig(
                thread_size="M4",
                category="SKRUV",
                tool_type="custom",
                tool_size="3",
                custom_tool_icon_path=icon_path,
            )
            img_a = self.renderer.render_fastener(cfg_a)
            self.assertEqual(img_a.size[1], 64)
            self.assertEqual(img_a.mode, "1")

            # Component with custom icon
            cfg_b = ComponentLabelConfig(
                category_banner="CUSTOM",
                spec_primary="PART-99",
                icon_type="custom",
                custom_icon_path=icon_path,
            )
            img_b = self.renderer.render_component(cfg_b)
            self.assertEqual(img_b.size[1], 64)
            self.assertEqual(img_b.mode, "1")


if __name__ == "__main__":
    unittest.main()

