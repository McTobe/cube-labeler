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
from core.label_renderer import BATCH_GAP_DOTS, LabelConfig, LabelRenderer


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

    def test_every_queued_label_has_equal_cut_margins(self):
        configs = [
            LabelConfig(text="Test"),
            LabelConfig(text="1"),
            LabelConfig(inventory_config=build_presets("en")["A2"].config),
        ]
        widths = [self.renderer._render_base_canvas(c)[0].width for c in configs]
        strip = self.renderer.render_batch(configs)[0].convert("L")
        margin = BATCH_GAP_DOTS // 2

        # Cut lines: both strip ends and the middle of each gap
        cuts, x = [0], margin
        for i, width in enumerate(widths):
            x += width
            cuts.append(x + margin if i < len(widths) - 1 else strip.width - 1)
            x += BATCH_GAP_DOTS
        for cut in cuts:
            dark = sum(1 for y in range(strip.height) if strip.getpixel((cut, y)) < 128)
            self.assertGreater(dark, 0, f"no cut line at x={cut}")

        for i in range(len(configs)):
            region = strip.crop((cuts[i] + 1, 0, cuts[i + 1], strip.height))
            left, _, right, _ = _ink_bbox(region)
            self.assertLessEqual(abs(left - (region.width - right)), 2, f"label {i}")
            self.assertGreaterEqual(left, margin - 1, f"label {i} too close to its cut line")


if __name__ == "__main__":
    unittest.main()
