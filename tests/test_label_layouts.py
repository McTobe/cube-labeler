#!/usr/bin/env python3
"""
Tests for the port strip (numbers that line up with the ports of a patch panel or switch) and
the cable flag (the text twice, with tape between that goes round a cable).
"""

import math
import os
import sys
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from core.label_renderer import BATCH_GAP_DOTS, LabelConfig, LabelRenderer
from core.specs import DOT_PITCH_MM, get_tape_spec


def _ink_columns(canvas, top, bottom):
    """x of every column with ink between rows top and bottom."""
    gray = canvas.convert("L")
    return [x for x in range(gray.width) if any(gray.getpixel((x, y)) < 128 for y in range(top, bottom))]


def _runs(columns):
    """Columns next to each other, as (first, last) runs."""
    runs = []
    for x in columns:
        if runs and x == runs[-1][1] + 1:
            runs[-1][1] = x
        else:
            runs.append([x, x])
    return runs


class TestPortStrip(unittest.TestCase):
    def setUp(self):
        self.renderer = LabelRenderer()

    def _canvas(self, **options):
        return self.renderer._render_base_canvas(LabelConfig(layout="ports", **options))

    def test_the_strip_is_exactly_as_long_as_its_ports(self):
        for count, pitch in ((12, 19.0), (24, 19.0), (8, 14.0), (6, 17.3)):
            canvas = self._canvas(port_count=count, port_pitch_mm=pitch)[0]
            self.assertEqual(canvas.width, round(count * pitch / DOT_PITCH_MM), (count, pitch))
            # Printed, it gets the same blank tape before and after as any label
            metrics = self.renderer.render(LabelConfig(layout="ports", port_count=count, port_pitch_mm=pitch))[3]
            self.assertAlmostEqual(metrics.print_length_mm, count * pitch + BATCH_GAP_DOTS * DOT_PITCH_MM, delta=0.15)

    def test_dividers_sit_within_half_a_dot_of_every_port_edge(self):
        # The error of rounding each port to whole dots must not add up along the strip
        pitch = 19.0
        canvas, _, border, printable_h, _, _ = self._canvas(port_count=24, port_pitch_mm=pitch, port_names="",
                                                            port_use_names=True)
        dividers = _runs(_ink_columns(canvas, border, border + printable_h))
        self.assertEqual(len(dividers), 23)
        for i, (first, last) in enumerate(dividers, start=1):
            middle = (first + last + 1) / 2
            self.assertLessEqual(abs(middle - i * pitch / DOT_PITCH_MM), 1.0, f"divider {i}")

    def test_thicker_dividers_between_groups(self):
        canvas, _, border, printable_h, _, _ = self._canvas(port_count=12, port_use_names=True, port_divider_every=6)
        widths = [last - first + 1 for first, last in _runs(_ink_columns(canvas, border, border + printable_h))]
        self.assertEqual(len(widths), 11)
        self.assertGreater(widths[5], widths[0])
        self.assertEqual(len(set(widths[:5] + widths[6:])), 1)

    def test_each_number_is_in_the_middle_of_its_port(self):
        pitch = 19.0
        canvas, _, border, printable_h, _, _ = self._canvas(port_count=6, port_pitch_mm=pitch)
        # Rows away from the dividers' ends see the digits and the dividers; the dividers are 2 dots wide
        runs = _runs(_ink_columns(canvas, border + 10, border + printable_h - 10))
        edges = [i * pitch / DOT_PITCH_MM for i in range(7)]
        for port in range(6):
            inside = [r for r in runs if edges[port] + 4 < r[0] and r[1] < edges[port + 1] - 4]
            self.assertTrue(inside, f"port {port + 1} has no number")
            middle = (inside[0][0] + inside[-1][1] + 1) / 2
            self.assertLessEqual(abs(middle - (edges[port] + edges[port + 1]) / 2), 2, f"port {port + 1}")

    def test_numbers_names_and_prefix(self):
        texts = self.renderer.port_texts
        self.assertEqual(texts(LabelConfig(port_count=6, port_first=7)), ["7", "8", "9", "10", "11", "12"])
        self.assertEqual(texts(LabelConfig(port_count=6, port_prefix="A")), ["A1", "A2", "A3", "A4", "A5", "A6"])
        named = LabelConfig(port_count=6, port_use_names=True, port_names="NAS\nRouter\n\nOffice\nTV\nHall\nToo many")
        self.assertEqual(texts(named), ["NAS", "Router", "", "Office", "TV", "Hall"])

    def test_every_port_gets_the_same_size_and_long_names_fit(self):
        cfg = LabelConfig(layout="ports", port_count=6, port_pitch_mm=14.0, port_use_names=True,
                          port_names="NAS\nThe living room TV\nAP")
        canvas, _, border, printable_h, _, size = self.renderer._render_base_canvas(cfg)
        self.assertGreater(size, 4)
        # The long name stays between its dividers
        pitch = 14.0 / DOT_PITCH_MM
        runs = _runs(_ink_columns(canvas, border + 4, border + printable_h - 4))
        self.assertTrue([r for r in runs if pitch + 3 < r[0] and r[1] < 2 * pitch - 3])
        # Its ink never runs into the dividers either side
        for edge in (pitch, 2 * pitch):
            divider = next(r for r in runs if r[0] <= edge <= r[1] + 1)
            self.assertLessEqual(divider[1] - divider[0] + 1, 3)

    def test_a_text_size_too_big_for_the_ports_fits_instead(self):
        cfg = LabelConfig(layout="ports", port_count=6, port_pitch_mm=14.0, port_use_names=True,
                          port_names="Kitchen\nOffice", text_height_mm=7, text_height_fallback=True)
        metrics = self.renderer.render(cfg)[3]
        self.assertTrue(metrics.text_height_fell_back)
        self.assertLess(metrics.max_text_height_mm, 7)
        small = self.renderer.render(LabelConfig(layout="ports", port_count=6, text_height_mm=3,
                                                 text_height_fallback=True))[3]
        self.assertFalse(small.text_height_fell_back)

    def test_works_on_every_tape(self):
        for tape in (12.0, 9.0, 6.0, 3.5):
            canvas = self._canvas(port_count=8, tape_width_mm=tape)[0]
            self.assertEqual(canvas.height, get_tape_spec(tape)["canvas_height"])

    def test_queued_port_strip_keeps_its_length(self):
        strip = LabelConfig(layout="ports", port_count=12)
        spans = []
        self.renderer.render_batch([LabelConfig(text="A"), strip], spans=spans)
        start, end = spans[1]
        self.assertEqual(end - start, round(12 * 19.0 / DOT_PITCH_MM))


class TestCableFlag(unittest.TestCase):
    def setUp(self):
        self.renderer = LabelRenderer()

    def test_the_text_twice_with_the_cable_between(self):
        text = LabelConfig(text="ETH 1")
        side = self.renderer._render_base_canvas(text)[0]
        for cable in (4.0, 6.0, 8.0):
            flag = self.renderer._render_base_canvas(LabelConfig(text="ETH 1", layout="flag", flag_cable_mm=cable,
                                                                 flag_fold_marks=False))[0]
            wrap = round(math.pi * cable / DOT_PITCH_MM)
            self.assertEqual(flag.width, 2 * side.width + wrap, cable)
            # Both sides read the same way round, so each one is the text label as it is
            self.assertEqual(flag.crop((0, 0, side.width, side.height)).tobytes(), side.convert("RGB").tobytes())
            second = flag.crop((side.width + wrap, 0, flag.width, side.height))
            self.assertEqual(second.tobytes(), side.convert("RGB").tobytes())
            self.assertIsNone(flag.convert("L").point(lambda p: 255 if p < 128 else 0)
                              .crop((side.width, 0, side.width + wrap, side.height)).getbbox())

    def test_fold_marks_at_both_ends_of_the_wrap(self):
        cfg = LabelConfig(text="ETH 1", layout="flag", flag_cable_mm=6.0)
        flag, _, border, printable_h, _, _ = self.renderer._render_base_canvas(cfg)
        side = self.renderer._render_base_canvas(LabelConfig(text="ETH 1"))[0].width
        wrap = round(math.pi * 6.0 / DOT_PITCH_MM)
        marks = _ink_columns(flag.crop((side, 0, side + wrap, flag.height)), border, border + printable_h)
        self.assertEqual(marks, [0, wrap - 1])

    def test_each_side_can_have_a_set_length(self):
        flag = self.renderer._render_base_canvas(LabelConfig(text="ETH 1", layout="flag", flag_side_mm=30))[0]
        side = round(30 / DOT_PITCH_MM)
        self.assertEqual(flag.width, 2 * side + round(math.pi * 6.0 / DOT_PITCH_MM))
        metrics = self.renderer.render(LabelConfig(text="A much longer name", layout="flag", flag_side_mm=10))[3]
        self.assertIn("cut off at 10 mm", metrics.warning)

    def test_text_size_and_extras_carry_over(self):
        metrics = self.renderer.render(LabelConfig(text="H", layout="flag", text_height_mm=5))[3]
        self.assertIsNotNone(metrics.max_text_height_mm)
        qr = LabelConfig(text="ETH 1", layout="flag", qr_enabled=True, qr_data="x")
        self.assertGreater(self.renderer._render_base_canvas(qr)[0].width,
                           self.renderer._render_base_canvas(LabelConfig(text="ETH 1", layout="flag"))[0].width)


if __name__ == "__main__":
    unittest.main()
