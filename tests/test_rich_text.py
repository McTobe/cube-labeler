#!/usr/bin/env python3
"""
Tests for styled label text: the markdown it is written in, the editor's helpers
and how the renderer draws sizes, styles, columns and frames.
"""

import os
import sys
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from core import rich_text as rt
from core.font_manager import FontManager
from core.label_renderer import LabelConfig, LabelRenderer

ROBOTO = os.path.join(BASE_DIR, "tests", "fonts", "Roboto-Regular.ttf")


def _styles(runs):
    return [(r.text, r.bold, r.italic, r.underline, r.invert) for r in runs]


class TestParsing(unittest.TestCase):
    def test_inline_styles(self):
        runs = rt.parse_inline("**M3** *x* __8__ ==hot==")
        self.assertEqual(_styles(runs), [
            ("M3", True, False, False, False),
            (" ", False, False, False, False),
            ("x", False, True, False, False),
            (" ", False, False, False, False),
            ("8", False, False, True, False),
            (" ", False, False, False, False),
            ("hot", False, False, False, True),
        ])

    def test_bold_italic_together(self):
        self.assertEqual(_styles(rt.parse_inline("***both***")), [("both", True, True, False, False)])

    def test_unmatched_and_spaced_markers_stay_text(self):
        for text in ("M3 * 8", "5 ** 2", "a == b", "snake__case", "**open"):
            with self.subTest(text):
                self.assertEqual(rt.plain_text(text), text)

    def test_backslash_keeps_a_marker(self):
        self.assertEqual(rt.plain_text(r"\*x\*"), "*x*")
        self.assertEqual(rt.parse(r"\# 5").lines[0].size, "normal")
        self.assertEqual(rt.plain_text("\\---"), "---")

    def test_line_prefixes(self):
        doc = rt.parse("# Big\n## Mid\n-# Small\n>> right\n# << both\nplain")
        self.assertEqual([(l.size, l.align, l.text) for l in doc.lines], [
            ("large", None, "Big"),
            ("medium", None, "Mid"),
            ("small", None, "Small"),
            ("normal", "right", "right"),
            ("large", "left", "both"),
            ("normal", None, "plain"),
        ])

    def test_hash_without_space_is_text(self):
        self.assertEqual(rt.parse("#42 Shelf").lines[0].text, "#42 Shelf")

    def test_columns(self):
        doc = rt.parse("M3\n---\n8 mm\nDIN 912")
        self.assertEqual([[l.text for l in col] for col in doc.columns], [["M3"], ["8 mm", "DIN 912"]])
        self.assertEqual(len(rt.parse("---\nA").columns), 1)

    def test_size_in_mm(self):
        line = rt.parse_line("[3.5mm] << Shelf")
        self.assertEqual((line.mm, line.align, line.text), (3.5, "left", "Shelf"))
        self.assertEqual(rt.parse_line(">> [2,5mm] A").mm, 2.5)  # either order, comma or point
        self.assertEqual(rt.parse_line("[3 mm] A").mm, 3.0)
        # A marker needs its space; an escaped bracket is text
        self.assertEqual(rt.parse_line("[3mm]A").text, "[3mm]A")
        self.assertEqual(rt.parse_line("\\[3mm] A").text, "[3mm] A")
        self.assertIsNone(rt.parse_line("[A1] Shelf").mm)

    def test_literal_newline_escape(self):
        self.assertEqual(len(rt.parse("A\\nB").lines), 2)


class TestEditingHelpers(unittest.TestCase):
    def test_toggle_adds_and_removes(self):
        text, s, e = rt.toggle_style("M3 screw", 0, 2, "bold")
        self.assertEqual((text, text[s:e]), ("**M3** screw", "M3"))
        self.assertEqual(rt.toggle_style(text, s, e, "bold"), ("M3 screw", 0, 2))
        # Selecting the markers too also removes them
        self.assertEqual(rt.toggle_style(text, 0, 6, "bold")[0], "M3 screw")

    def test_italic_and_bold_do_not_mix_up(self):
        text = "**M3**"
        self.assertEqual(rt.toggle_style(text, 2, 4, "italic")[0], "***M3***")
        self.assertEqual(rt.toggle_style("***M3***", 3, 5, "italic")[0], "**M3**")
        self.assertEqual(rt.toggle_style("***M3***", 3, 5, "bold")[0], "*M3*")

    def test_toggle_with_no_selection_inserts_a_pair(self):
        text, s, e = rt.toggle_style("ab", 1, 1, "invert")
        self.assertEqual((text, s, e), ("a====b", 3, 3))

    def test_set_line_style(self):
        self.assertEqual(rt.set_line_style("Shelf", size="large"), "# Shelf")
        self.assertEqual(rt.set_line_style("# Shelf", align="right"), "# >> Shelf")
        self.assertEqual(rt.set_line_style("# >> Shelf", size="small"), "-# >> Shelf")
        self.assertEqual(rt.set_line_style("-# >> Shelf", size="normal", align=None), "Shelf")
        self.assertEqual(rt.line_style(">> # Shelf"), ("large", "right"))

    def test_set_line_size_in_mm(self):
        self.assertEqual(rt.set_line_style("<< Shelf", size=3.5), "[3.5mm] << Shelf")
        self.assertEqual(rt.set_line_style("# Shelf", size=2), "[2mm] Shelf")
        self.assertEqual(rt.set_line_style("[2mm] >> Shelf", size=2.25), "[2.25mm] >> Shelf")
        self.assertEqual(rt.set_line_style("[2mm] >> Shelf", size="normal"), ">> Shelf")
        self.assertEqual(rt.set_line_style("[2mm] Shelf", align="left"), "[2mm] << Shelf")
        self.assertEqual(rt.line_style("[2.5mm] >> Shelf"), (2.5, "right"))


class TestStyledFonts(unittest.TestCase):
    def test_missing_styles_are_faked(self):
        mgr = FontManager()
        _, fake_bold, fake_italic = mgr.load_styled_font(ROBOTO, 20, bold=True, italic=True)
        self.assertTrue(fake_bold and fake_italic)

    def test_installed_bold_file_is_used(self):
        mgr = FontManager()
        mgr._font_cache = {"Roboto": ROBOTO, "Roboto Bold": ROBOTO + "?bold"}
        mgr._loaded_fonts[f"{ROBOTO}?bold::20"] = "bold font"
        font, fake_bold, fake_italic = mgr.load_styled_font("Roboto", 20, bold=True, italic=True)
        self.assertEqual((font, fake_bold, fake_italic), ("bold font", False, True))


def _dark_columns(img):
    gray = img.convert("L")
    return [x for x in range(gray.width) if any(gray.getpixel((x, y)) < 128 for y in range(gray.height))]


class TestRendering(unittest.TestCase):
    def setUp(self):
        self.renderer = LabelRenderer()

    def _text(self, text, **kw):
        cfg = LabelConfig(text=text, font_name=ROBOTO, cut_line=False, **kw)
        return self.renderer._render_base_canvas(cfg)

    def test_plain_text_still_fills_the_tape(self):
        canvas, _, border, printable_h, _, size = self._text("Test")
        bbox = canvas.convert("L").point(lambda p: 255 if p < 128 else 0).getbbox()
        self.assertGreaterEqual(bbox[3] - bbox[1], printable_h - 3)

    def test_large_line_is_bigger_than_small_line(self):
        layout = rt.TextLayout(rt.parse("# Big\n-# Small"), ROBOTO)
        big, small = (layout.render_line(line, 30) for line in layout.doc.lines)
        self.assertGreater(big.height, small.height * 2)

    def test_mixed_sizes_fit_the_tape(self):
        for text in ("# M3 SCREWS\n-# 8 mm", "## A\nB\n-# C", "==X==\n__Y__"):
            with self.subTest(text):
                canvas, _, border, printable_h, _, _ = self._text(text)
                bbox = canvas.convert("L").point(lambda p: 255 if p < 128 else 0).getbbox()
                self.assertGreaterEqual(bbox[1], border)
                self.assertLessEqual(bbox[3], border + printable_h)

    def test_script_fonts_keep_ink_outside_the_advance(self):
        # Pacifico's "L" starts left of the pen and its "l" ends right of the advance
        from PIL import Image, ImageDraw
        pacifico = os.path.join(BASE_DIR, "web", "fonts", "Pacifico-Regular.ttf")
        for text in ("Luleå", "Mjöl", "fjord"):
            with self.subTest(text):
                layout = rt.TextLayout(rt.parse(text), pacifico)
                layout_font = FontManager().load_font(pacifico, 40)
                ref = Image.new("L", (400, 160), 0)
                ImageDraw.Draw(ref).text((80, 100), text, font=layout_font, fill=255, anchor="ls")
                ink = lambda img: sum(1 for p in img.tobytes() if p > 127)
                self.assertEqual(ink(layout.render(40)), ink(ref))

    def test_bold_is_wider(self):
        plain = self._text("Shelf", auto_fit_font=False, fixed_font_size=30)[0]
        bold = self._text("**Shelf**", auto_fit_font=False, fixed_font_size=30)[0]
        self.assertGreater(bold.width, plain.width)

    def test_inverted_text_draws_a_black_block(self):
        canvas = self._text("==HOT==")[0].convert("L")
        dark = sum(1 for p in canvas.tobytes() if p < 128)
        self.assertGreater(dark, canvas.width * canvas.height // 4)

    def test_columns_get_a_divider(self):
        canvas = self._text("A\n---\nB")[0]
        dark = _dark_columns(canvas)
        # A, the divider and B are three separate groups of ink
        groups = 1 + sum(1 for a, b in zip(dark, dark[1:]) if b > a + 1)
        self.assertEqual(groups, 3)

    def test_columns_share_a_middle(self):
        # A line box leaves room for every descender in the label ("j" here), so centring the
        # boxes let a lone capital column ride high next to a two-line one (issue seen in Open Sans)
        open_sans = os.path.join(BASE_DIR, "web", "fonts", "OpenSans-Regular.ttf")
        for font in (ROBOTO, open_sans):
            with self.subTest(font):
                layout = rt.TextLayout(rt.parse("# BECO\n---\n-# << Tobias Kejonen\n-# << 072 225 27 24"), font)
                img = layout.render(40)
                widths = [layout._render_column(col, 40).width for col in layout.doc.columns]
                left = img.crop((0, 0, widths[0], img.height)).getbbox()
                right = img.crop((img.width - widths[1], 0, img.width, img.height)).getbbox()
                self.assertLessEqual(abs((left[1] + left[3]) - (right[1] + right[3])), 2)

    def test_line_in_mm_keeps_its_size_and_the_rest_fits(self):
        layout = rt.TextLayout(rt.parse("Big\n---\n[2mm] Small\n[2mm] Lines"), ROBOTO)
        two_mm = layout.size_for_cap_height(2 / rt.DOT_MM)
        base = layout.fit_size(64)
        self.assertEqual([layout._size(l, base) for l in layout.doc.lines[1:]], [two_mm, two_mm])
        self.assertLessEqual(layout.height(base), 64)
        self.assertGreater(layout.cap_height(base), layout.cap_height(two_mm) * 2)

    def test_lines_in_mm_too_tall_leave_the_rest_readable(self):
        layout = rt.TextLayout(rt.parse("Big\n---\n[6mm] A\n[6mm] B"), ROBOTO)
        loose = rt.TextLayout(rt.parse("Big\n---\nA\nB"), ROBOTO)
        self.assertEqual(layout.fit_size(64), loose.fit_size(64))

    def test_columns_in_mm_keep_a_normal_gap(self):
        # With every line in mm the base sizes nothing, so the divider's gap follows the biggest line
        sized = rt.TextLayout(rt.parse("[6mm] BECO\n---\n[2.5mm] Tobias\n[2.5mm] 072"), ROBOTO)
        base = sized.fit_size(64)
        big = sized._size(sized.doc.lines[0], base)
        self.assertEqual(base, big)
        widths = sum(sized._render_column(c, base).width for c in sized.doc.columns)
        gap = sized.render(base).width - widths
        self.assertEqual(gap, 2 * max(6, round(big * 0.3)) + max(1, round(big * 0.05)))

    def test_text_size_leaves_lines_in_mm_alone(self):
        text = "[6mm] BECO\n---\n[2.5mm] Tobias\n[2.5mm] 072"
        shots = [self.renderer.render(LabelConfig(text=text, font_name=ROBOTO, text_height_mm=mm, text_height_fallback=True, font_scale=80, cut_line=False))
                 for mm in (None, 3, 7)]
        self.assertEqual(shots[0][0].tobytes(), shots[1][0].tobytes())
        self.assertEqual(shots[0][0].tobytes(), shots[2][0].tobytes())
        self.assertIsNone(shots[2][3].max_text_height_mm)
        self.assertFalse(shots[2][3].text_height_fell_back)

    def test_metrics_give_each_line_its_size(self):
        text = "Big\n---\n[2.5mm] Small\n-# Smaller"
        _, _, _, metrics = self.renderer.render(LabelConfig(text=text, font_name=ROBOTO))
        sizes, tallest = metrics.line_sizes_mm, metrics.line_max_mm
        self.assertEqual(len(sizes), 4)
        self.assertEqual((sizes[1], tallest[1], sizes[2]), (None, None, 2.5))
        self.assertGreater(sizes[0], sizes[2])
        self.assertGreater(tallest[2], sizes[2])
        self.assertIsNone(metrics.warning)
        _, _, _, metrics = self.renderer.render(LabelConfig(text="[8mm] A\n[8mm] B", font_name=ROBOTO))
        self.assertIn("taller together", metrics.warning)

    def test_frame_surrounds_the_content(self):
        for frame in ("box", "rounded"):
            with self.subTest(frame):
                fixed = dict(auto_fit_font=False, fixed_font_size=30)
                canvas, _, border, printable_h, _, _ = self._text("Spices", frame=frame, **fixed)
                plain = self._text("Spices", **fixed)[0]
                self.assertGreater(canvas.width, plain.width)
                gray = canvas.convert("L")
                mid_x = canvas.width // 2
                self.assertLess(gray.getpixel((mid_x, border)), 128)
                self.assertLess(gray.getpixel((mid_x, border + printable_h - 1)), 128)

    def test_alignment_per_line(self):
        layout = rt.TextLayout(rt.parse("<< ab\nabcdefgh\n>> ab"), ROBOTO)
        block = layout.render(30)
        lines = [layout.render_line(line, 30) for line in layout.doc.lines]
        top = block.crop((0, 0, block.width, lines[0].height)).getbbox()
        gap = layout._gap(lines[0].height, lines[1].height) + layout._gap(lines[1].height, lines[2].height)
        bottom_y = lines[0].height + lines[1].height + gap
        bottom = block.crop((0, bottom_y, block.width, block.height)).getbbox()
        self.assertEqual(top[0], 0)
        self.assertEqual(bottom[2], block.width)


if __name__ == "__main__":
    unittest.main()
