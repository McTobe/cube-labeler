#!/usr/bin/env python3
"""
Tests that text is centred on its ink and that every label in a queue strip
has the same space on both sides of its cut lines.
"""

import os
import sys
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from core.label_language import build_presets
from core.label_renderer import BATCH_GAP_DOTS, SINGLE_BIN_PADDING_MM, LabelConfig, LabelRenderer
from core.specs import DOT_PITCH_MM


def _ink_bbox(img):
    return img.convert("L").point(lambda p: 255 if p < 128 else 0).getbbox()


class TestLabelSpacing(unittest.TestCase):
    def setUp(self):
        self.renderer = LabelRenderer()

    def test_text_is_centred_on_its_ink(self):
        # "1" has a large left side bearing in most fonts, which used to push it right
        for text in ("1", "Test", "Wi", "1\n22"):
            canvas = self.renderer._render_base_canvas(LabelConfig(text=text))[0]
            left, _, right, _ = _ink_bbox(canvas)
            self.assertLessEqual(abs(left - (canvas.width - right)), 1, text)

    def test_text_height_in_mm_is_the_capital_letter_height(self):
        # The same size on any tape and with any length of text, and Text scale leaves it alone
        for tape, text in ((12.0, "HELLO"), (9.0, "H"), (6.0, "HI")):
            cfg = LabelConfig(text=text, tape_width_mm=tape, text_height_mm=4, font_scale=150)
            _, top, _, bottom = _ink_bbox(self.renderer._render_base_canvas(cfg)[0])
            self.assertAlmostEqual((bottom - top) * DOT_PITCH_MM, 4, delta=0.2, msg=text)

    def test_text_too_tall_for_the_tape_warns(self):
        metrics = self.renderer.render(LabelConfig(text="H\nH", text_height_mm=7))[3]
        self.assertIn("7 mm", metrics.warning)
        self.assertIsNone(self.renderer.render(LabelConfig(text="H", text_height_mm=7))[3].warning)

    def test_leading_spaces_still_indent(self):
        cfg = LabelConfig(text="Shelf A\n    Box 1", alignment="left", auto_fit_font=False, fixed_font_size=20)
        canvas = self.renderer._render_base_canvas(cfg)[0]
        half = canvas.height // 2
        top = _ink_bbox(canvas.crop((0, 0, canvas.width, half)))
        bottom = _ink_bbox(canvas.crop((0, half, canvas.width, canvas.height)))
        self.assertGreater(bottom[0], top[0] + 10)

    def test_single_bin_label_has_side_padding(self):
        cfg = LabelConfig(inventory_config=build_presets("en")["A2"].config, cut_line=False)
        preview = self.renderer.render(cfg)[0]
        left, _, right, _ = _ink_bbox(preview)
        pad = round(SINGLE_BIN_PADDING_MM / DOT_PITCH_MM)
        self.assertEqual(left, pad)
        self.assertEqual(preview.width - right, pad)

    def test_single_label_matches_a_queued_one(self):
        # Same half-gap as in a queue, a cut line at the start and none at the end
        cfg = LabelConfig(inventory_config=build_presets("en")["A2"].config)
        canvas = self.renderer._render_base_canvas(cfg)[0]
        preview = self.renderer.render(cfg)[0].convert("L")
        margin = BATCH_GAP_DOTS // 2
        self.assertEqual(preview.width, canvas.width + 2 * margin)
        column = lambda x: sum(1 for y in range(preview.height) if preview.getpixel((x, y)) < 128)
        self.assertGreater(column(0), 0)
        self.assertEqual(column(preview.width - 1), 0)

    def test_every_queued_label_has_equal_cut_margins(self):
        configs = [
            LabelConfig(text="Test"),
            LabelConfig(text="1"),
            LabelConfig(inventory_config=build_presets("en")["A2"].config),
        ]
        widths = [self.renderer._render_base_canvas(c)[0].width for c in configs]
        strip = self.renderer.render_batch(configs)[0].convert("L")
        margin = BATCH_GAP_DOTS // 2

        # Cut lines: the strip start and the middle of each gap. The strip end has none,
        # since it stops at the cutter.
        cuts, x = [0], margin
        for i, width in enumerate(widths):
            x += width
            cuts.append(x + margin if i < len(widths) - 1 else strip.width - 1)
            x += BATCH_GAP_DOTS
        dark = lambda cut: sum(1 for y in range(strip.height) if strip.getpixel((cut, y)) < 128)
        for cut in cuts[:-1]:
            self.assertGreater(dark(cut), 0, f"no cut line at x={cut}")
        self.assertEqual(dark(cuts[-1]), 0, "the strip end should have no cut line")

        for i in range(len(configs)):
            region = strip.crop((cuts[i] + 1, 0, cuts[i + 1], strip.height))
            left, _, right, _ = _ink_bbox(region)
            self.assertLessEqual(abs(left - (region.width - right)), 2, f"label {i}")
            self.assertGreaterEqual(left, margin - 1, f"label {i} too close to its cut line")


if __name__ == "__main__":
    unittest.main()
