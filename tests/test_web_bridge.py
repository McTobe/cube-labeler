#!/usr/bin/env python3
"""
Tests for web/cube_web.py, the Python side of the web app. It runs in Pyodide in the browser,
but it is plain Python, so CPython checks it here against the desktop printer driver.
"""

import io
import os
import sys
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for path in (BASE_DIR, os.path.join(BASE_DIR, "web"), os.path.dirname(os.path.abspath(__file__))):
    if path not in sys.path:
        sys.path.insert(0, path)

from PIL import Image

import cube_web
from core.label_renderer import LabelConfig, LabelRenderer
from core.printer import BrotherPrinter
from test_audit_fixes import FakeSerial, _status_bytes


class TestWebRender(unittest.TestCase):
    def test_render_matches_desktop_renderer(self):
        result = cube_web.render_label({"text": "M3 x 12", "tape_width_mm": 9.0, "font_name": "Arial"})
        _, _, raster, metrics = LabelRenderer().render(
            LabelConfig(text="M3 x 12", tape_width_mm=9.0, font_name="Arial")
        )
        self.assertEqual(result["raster"], raster)
        self.assertEqual(result["metrics"]["raster_lines"], metrics.raster_lines)
        self.assertEqual(Image.open(io.BytesIO(result["preview_png"])).format, "PNG")

    def test_unknown_options_are_ignored(self):
        result = cube_web.render_label({"text": "Hi", "not_a_field": 1})
        self.assertGreater(cube_web.raster_lines(result["raster"]), 0)

    def test_add_font_rejects_non_fonts(self):
        self.assertIsNone(cube_web.add_font("notes.ttf", b"not a font"))

    def test_add_font_registers_bundled_font(self):
        with open(os.path.join(BASE_DIR, "web", "fonts", "Arimo-Bold.ttf"), "rb") as f:
            name = cube_web.add_font("Arimo-Bold.ttf", f.read())
        self.assertEqual(name, "[Custom] Arimo-Bold")
        self.assertIn(name, cube_web.font_names())


class TestWebPrintJob(unittest.TestCase):
    RASTER = bytes([0xFF] * 16) + bytes(16) + bytes(range(16))

    def _desktop_bytes(self, **kwargs):
        fake = FakeSerial([_status_bytes(), _status_bytes(status_type=0x01)])
        printer = BrotherPrinter("COM_TEST_WEB")
        printer.connect = lambda: setattr(printer, "_ser", fake)
        printer.print_raster_data(self.RASTER, **kwargs)
        return bytes(fake.written)

    def _web_bytes(self, options):
        # The same sequence printer.js sends: status query, job, print, then a reset on close
        return (
            cube_web.status_query()
            + cube_web.print_job(_status_bytes(), self.RASTER, options)
            + cube_web.print_command()
            + cube_web.reset_sequence()
        )

    def test_job_bytes_match_desktop_driver(self):
        cases = [
            ({}, {}),
            ({"auto_cut": True}, {"auto_cut": True}),
            ({"auto_cut": False, "compress": False}, {"auto_cut": False, "nocomp": True}),
            ({"auto_cut": True, "end_margin": 14, "chaining": True},
             {"auto_cut": True, "end_margin": 14, "no_feed": True}),
        ]
        for web_opts, desktop_kwargs in cases:
            with self.subTest(web_opts):
                self.assertEqual(self._web_bytes(web_opts), self._desktop_bytes(**desktop_kwargs))

    def test_wrong_tape_width_is_refused(self):
        with self.assertRaisesRegex(RuntimeError, "needs 12mm tape; 9mm is loaded"):
            cube_web.print_job(_status_bytes(tape_width=9), self.RASTER, {"required_tape_width_mm": 12})

    def test_not_ready_is_refused(self):
        with self.assertRaisesRegex(RuntimeError, "not ready: .*Cover opened"):
            cube_web.print_job(_status_bytes(err=1 << 4), self.RASTER)

    def test_bad_raster_is_refused(self):
        with self.assertRaises(ValueError):
            cube_web.print_job(_status_bytes(), b"\x00" * 10)

    def test_job_state(self):
        self.assertEqual(cube_web.job_state(_status_bytes(status_type=0x01)), "completed")
        self.assertEqual(cube_web.job_state(_status_bytes(status_type=0x06, phase_type=1)), "pending")
        self.assertEqual(cube_web.job_state(b"\x00" * 32), "invalid")
        with self.assertRaisesRegex(RuntimeError, "Cover opened"):
            cube_web.job_state(_status_bytes(status_type=0x02, err=1 << 4))

    def test_describe_status(self):
        status = cube_web.describe_status(_status_bytes(tape_width=9))
        self.assertEqual(status["tape_width_mm"], 9)
        self.assertTrue(status["is_ready"])
        self.assertEqual(status["errors"], [])


if __name__ == "__main__":
    unittest.main()
