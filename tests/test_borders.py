"""
Borders (core/borders.py) and vertical or turned text: every border draws inside its label
and keeps clear of the text, and vertical text stacks its letters.
"""
import os
import sys
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from core import borders
from core.label_renderer import LabelConfig, LabelRenderer

ROBOTO = os.path.join(BASE_DIR, "tests", "fonts", "Roboto-Regular.ttf")


def _ink(img):
    return img.convert("L").point(lambda p: 255 if p < 128 else 0)


class TestBorders(unittest.TestCase):
    def setUp(self):
        self.renderer = LabelRenderer()

    def _canvas(self, text="Spices", **kw):
        cfg = LabelConfig(text=text, font_name=ROBOTO, cut_line=False, **kw)
        return self.renderer._render_base_canvas(cfg)

    def test_ids_are_unique_and_categories_known(self):
        ids = [b.id for b in borders.BORDERS_LIST]
        self.assertEqual(len(ids), len(set(ids)))
        known = {c for c, _ in borders.CATEGORIES}
        for b in borders.BORDERS_LIST:
            self.assertIn(b.category, known, b.id)

    def test_every_category_fills_even_rows(self):
        # The picker shows 2 tiles a row on a phone and 4 on a wide screen, with no orphans
        for cat, _ in borders.CATEGORIES:
            count = sum(1 for b in borders.BORDERS_LIST if b.category == cat and b.id != "none")
            self.assertEqual(count % 4, 0, cat)

    def test_old_frames_still_work(self):
        self.assertEqual(borders.get("box").id, "box")
        self.assertEqual(borders.get("rounded").id, "rounded")
        self.assertEqual(borders.get("no-such-border").id, "none")

    def test_every_border_draws_and_leaves_the_middle_for_the_text(self):
        for b in borders.BORDERS_LIST:
            if b.id == "none":
                continue
            with self.subTest(b.id):
                mask = borders.render(b.id, 300, 64)
                self.assertEqual(mask.size, (300, 64))
                self.assertIsNotNone(mask.getbbox(), "draws nothing")
                ix, iy = b.insets(64)
                inner = mask.crop((ix + 1, iy + 1, 300 - ix - 1, 64 - iy - 1))
                self.assertIsNone(inner.getbbox(), "draws where the text goes")

    def test_border_goes_round_the_text(self):
        plain, _, border_y, printable_h, _, _ = self._canvas()
        framed = self._canvas(frame="stars")[0]
        self.assertGreater(framed.width, plain.width)
        top = _ink(framed).crop((0, border_y, framed.width, border_y + 2)).getbbox()
        self.assertIsNotNone(top)


class TestDirection(unittest.TestCase):
    def setUp(self):
        self.renderer = LabelRenderer()

    def _canvas(self, text, **kw):
        cfg = LabelConfig(text=text, font_name=ROBOTO, cut_line=False, **kw)
        return self.renderer._render_base_canvas(cfg)

    def test_vertical_letters_run_along_the_tape(self):
        canvas, _, border_y, printable_h, _, _ = self._canvas("ABCDEF", direction="vertical")
        bbox = _ink(canvas).getbbox()
        # Six upright letters one after the other along the tape, each as tall as the tape allows
        self.assertGreater(bbox[2] - bbox[0], 4 * (bbox[3] - bbox[1]))
        self.assertGreaterEqual(bbox[1], border_y)
        self.assertLessEqual(bbox[3], border_y + printable_h)

    def test_vertical_lines_become_columns(self):
        one = self._canvas("AB", direction="vertical")[0]
        two = self._canvas("AB\nCD", direction="vertical")[0]
        # Two columns share the tape height, so each letter is smaller and the label shorter
        self.assertLess(two.width, one.width)

    def test_turned_text_fits_across_the_tape(self):
        canvas, _, border_y, printable_h, _, _ = self._canvas("Mon", direction="turned")
        bbox = _ink(canvas).getbbox()
        self.assertGreaterEqual(bbox[1], border_y)
        self.assertLessEqual(bbox[3], border_y + printable_h)
        # Turned, the word is taller across the tape than it is long
        self.assertGreater(bbox[3] - bbox[1], bbox[2] - bbox[0])

    def test_empty_text_still_renders(self):
        for direction in ("vertical", "turned"):
            with self.subTest(direction):
                canvas = self._canvas("", direction=direction)[0]
                self.assertGreater(canvas.width, 0)


if __name__ == "__main__":
    unittest.main()
