#!/usr/bin/env python3
"""
Tests that Code 128 barcodes read back as what was typed, from the drawn bars, and that text
labels place them next to the text.
"""

import os
import sys
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from core import barcode
from core.label_renderer import LabelConfig, LabelRenderer


def _read_bars(img, module=barcode.MODULE_DOTS):
    """The text a scanner would read from a barcode image: bar widths back to symbols to text."""
    row = [img.getpixel((x, 0)) < 128 for x in range(img.width)]
    runs, x = [], row.index(True)
    end = len(row) - row[::-1].index(True)
    while x < end:
        start = x
        while x < end and row[x] == row[start]:
            x += 1
        runs.append((x - start) // module)
    assert "".join(map(str, runs[-7:])) == barcode.STOP
    symbols = [barcode.PATTERNS.index("".join(map(str, runs[i:i + 6]))) for i in range(0, len(runs) - 7, 6)]
    *values, check = symbols
    assert check == (values[0] + sum(v * n for n, v in enumerate(values[1:], 1))) % 103

    code = {barcode.START_A: "A", barcode.START_B: "B", barcode.START_C: "C"}[values[0]]
    text = ""
    for v in values[1:]:
        if code != "C" and v == barcode.CODE_C or code != "B" and v == barcode.CODE_B \
                or code != "A" and v == barcode.CODE_A:
            code = {barcode.CODE_A: "A", barcode.CODE_B: "B", barcode.CODE_C: "C"}[v]
        elif code == "C":
            text += f"{v:02d}"
        elif code == "A" and v >= 64:
            text += chr(v - 64)
        else:
            text += chr(v + 32)
    return text


class TestBarcode(unittest.TestCase):
    def test_reads_back(self):
        for data in ("PN-10432", "12345678", "1234567", "42", "A1", "0", "M3x12 bolt",
                     "abc123456789xyz", "SKU 00012345 A", "a12345", "Tab\there", "~{}|"):
            with self.subTest(data=data):
                self.assertEqual(_read_bars(barcode.render(data, 48, show_text=False)), data)

    def test_digits_are_packed_in_pairs(self):
        # Code set C: start, four pairs, check
        self.assertEqual(len(barcode.encode("12345678")), 6)
        # Text then an odd run of digits: one digit stays in B, the rest go in pairs
        self.assertEqual(barcode.encode("PN-10432")[:7], [104, 48, 46, 13, 17, 99, 4])

    def test_bars_keep_a_scannable_width_and_quiet_zones(self):
        img = barcode.render("PN-10432", 64, show_text=False)
        dark = [x for x in range(img.width) if img.getpixel((x, 0)) < 128]
        self.assertEqual(dark[0], barcode.QUIET_MODULES * barcode.MODULE_DOTS)
        self.assertEqual(img.width - 1 - dark[-1], barcode.QUIET_MODULES * barcode.MODULE_DOTS)
        self.assertGreaterEqual(barcode.MODULE_DOTS, 2)

    def test_text_under_the_bars_leaves_them_shorter(self):
        from core.font_manager import font_manager
        font = font_manager.load_font("Arial", 12)
        with_text = barcode.render("PN-10432", 64, True, font)
        x = barcode.QUIET_MODULES * barcode.MODULE_DOTS
        bar_rows = [y for y in range(64) if with_text.getpixel((x, y)) < 128]
        self.assertLess(len(bar_rows), 56)
        self.assertEqual(_read_bars(with_text), "PN-10432")

    def test_non_ascii_is_refused(self):
        self.assertEqual(barcode.unsupported_chars("M3×12 ×å"), "×å")
        self.assertIsNone(barcode.render("M3×12", 48))
        with self.assertRaises(ValueError):
            barcode.encode("M3×12")


class TestBarcodeOnLabel(unittest.TestCase):
    def setUp(self):
        self.renderer = LabelRenderer()

    def test_barcode_makes_the_label_longer(self):
        plain = self.renderer.render(LabelConfig(text="M3"))[3]
        coded = self.renderer.render(LabelConfig(text="M3", barcode_enabled=True, barcode_data="PN-10432"))[3]
        self.assertGreater(coded.print_length_mm, plain.print_length_mm + 30)
        self.assertIsNone(coded.warning)

    def test_fits_every_tape(self):
        for tape in (12.0, 9.0, 6.0, 3.5):
            with self.subTest(tape=tape):
                config = LabelConfig(text="", tape_width_mm=tape, barcode_enabled=True, barcode_data="12345678")
                self.assertIsNone(self.renderer.render(config)[3].warning)

    def test_unsupported_characters_warn(self):
        metrics = self.renderer.render(LabelConfig(text="M3", barcode_enabled=True, barcode_data="M3×12"))[3]
        self.assertIn("×", metrics.warning)

    def test_off_leaves_the_label_alone(self):
        plain = self.renderer.render(LabelConfig(text="M3"))[3]
        off = self.renderer.render(LabelConfig(text="M3", barcode_enabled=False, barcode_data="PN-10432"))[3]
        self.assertEqual(off.print_length_mm, plain.print_length_mm)


if __name__ == "__main__":
    unittest.main()
