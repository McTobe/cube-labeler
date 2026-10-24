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


class TestWebBuild(unittest.TestCase):
    def test_shipped_core_modules_bring_their_imports(self):
        import re
        import build
        core_dir = os.path.join(BASE_DIR, "core")
        for name in build.CORE_MODULES:
            with open(os.path.join(core_dir, name), encoding="utf-8") as f:
                source = f.read()
            imported = set(re.findall(r"^\s*from core\.(\w+) import", source, re.M))
            for names in re.findall(r"^\s*from core import ([\w, ]+)", source, re.M):
                imported.update(n.strip() for n in names.split(","))
            # Desktop-only imports inside functions are fine as long as the web path never reaches them
            imported -= {"config", "printer", "icon_manager", "secret_store"}
            for module in imported:
                with self.subTest(file=name, module=module):
                    self.assertIn(f"{module}.py", build.CORE_MODULES)


    def test_build_survives_folders_windows_will_not_delete(self):
        import tempfile
        from unittest import mock
        import build
        with tempfile.TemporaryDirectory() as tmp:
            dist = os.path.join(tmp, "dist")
            os.makedirs(os.path.join(dist, "js", "pages"))
            with open(os.path.join(dist, "js", "pages", "old.js"), "w") as f:
                f.write("stale")
            denied = OSError(13, "Access is denied")
            with mock.patch.object(build, "DIST_DIR", dist), mock.patch("os.rmdir", side_effect=denied):
                self.assertEqual(build.main(), 0)
            self.assertFalse(os.path.exists(os.path.join(dist, "js", "pages", "old.js")))
            self.assertTrue(os.path.isfile(os.path.join(dist, "js", "main.js")))
            self.assertTrue(os.path.isfile(os.path.join(dist, "sw.js")))


class TestWebRender(unittest.TestCase):
    def test_render_matches_desktop_renderer(self):
        result = cube_web.render_label({"text": "M3 x 12", "tape_width_mm": 9.0, "font_name": "Arial"})
        _, _, raster, metrics = LabelRenderer().render(
            LabelConfig(text="M3 x 12", tape_width_mm=9.0, font_name="Arial")
        )
        self.assertEqual(result["raster"], raster)
        self.assertEqual(result["metrics"]["raster_lines"], metrics.raster_lines)
        self.assertEqual(Image.open(io.BytesIO(result["preview_png"])).format, "PNG")

    def test_preview_leaves_out_the_cut_line(self):
        result = cube_web.render_label({"text": "Hi", "tape_bg_color": "#FFFFFF"})
        preview = Image.open(io.BytesIO(result["preview_png"])).convert("L")
        dots = Image.open(io.BytesIO(result["dots_png"])).convert("L")
        column = [preview.getpixel((0, y)) for y in range(preview.height)]
        self.assertEqual(min(column), 255)
        # The printer still prints it
        self.assertLess(min(dots.getpixel((0, y)) for y in range(dots.height)), 128)

    def test_unknown_options_are_ignored(self):
        result = cube_web.render_label({"text": "Hi", "not_a_field": 1})
        self.assertGreater(cube_web.raster_lines(result["raster"]), 0)

    def test_dots_view_reads_like_the_preview(self):
        result = cube_web.render_label({"text": "Wide label text", "tape_width_mm": 12.0})
        preview = Image.open(io.BytesIO(result["preview_png"]))
        dots = Image.open(io.BytesIO(result["dots_png"]))
        # The raster runs down the tape; turned back, it is as long as the label
        self.assertEqual(dots.width, result["metrics"]["raster_lines"])
        self.assertEqual(dots.height, 128)
        self.assertGreater(dots.width, dots.height)
        self.assertEqual(preview.width, dots.width)

    def test_picture_from_bytes(self):
        picture = Image.new("RGB", (40, 40), "white")
        picture.paste((0, 0, 0), (10, 10, 30, 30))
        data = io.BytesIO()
        picture.save(data, format="PNG")
        without = cube_web.render_label({"text": "Box"})
        with_picture = cube_web.render_label({"text": "Box", "image_data": data.getvalue()})
        self.assertGreater(with_picture["metrics"]["raster_lines"], without["metrics"]["raster_lines"])
        # The same picture again reuses its file
        again = cube_web.render_label({"text": "Box", "image_data": data.getvalue()})
        self.assertEqual(again["raster"], with_picture["raster"])

    def test_image_path_option_is_not_taken_from_the_page(self):
        result = cube_web.render_label({"text": "Hi", "image_path": "/etc/passwd"})
        self.assertEqual(result["raster"], cube_web.render_label({"text": "Hi"})["raster"])

    def test_add_font_rejects_non_fonts(self):
        self.assertIsNone(cube_web.add_font("notes.ttf", b"not a font"))

    def test_add_font_registers_bundled_font(self):
        with open(os.path.join(BASE_DIR, "web", "fonts", "Arimo-Bold.ttf"), "rb") as f:
            name = cube_web.add_font("Arimo-Bold.ttf", f.read())
        self.assertEqual(name, "[Custom] Arimo-Bold")
        self.assertIn(name, cube_web.font_names())


class TestWebTextEditing(unittest.TestCase):
    def test_toggle_style(self):
        self.assertEqual(cube_web.toggle_style("M3 screw", 0, 2, "bold"), ["**M3** screw", 2, 4])
        self.assertEqual(cube_web.toggle_style("**M3** screw", 2, 4, "bold"), ["M3 screw", 0, 2])

    def test_restyle_lines_touches_only_selected_lines(self):
        text = "Top\nMiddle\nBottom"
        self.assertEqual(cube_web.restyle_lines(text, 5, 5, {"size": "large"}), "Top\n# Middle\nBottom")
        self.assertEqual(cube_web.restyle_lines(text, 0, 6, {"align": "right"}), ">> Top\n>> Middle\nBottom")
        styled = "# >> Top"
        self.assertEqual(cube_web.restyle_lines(styled, 0, 0, {"align": None}), "# Top")
        self.assertEqual(cube_web.restyle_lines(styled, 0, 0, {"size": "normal"}), ">> Top")

    def test_line_style_at(self):
        text = "Plain\n-# << small left"
        self.assertEqual(cube_web.line_style_at(text, 0), ["normal", None])
        self.assertEqual(cube_web.line_style_at(text, len(text)), ["small", "left"])

    def test_blank_raster_feeds_the_desktop_length(self):
        from core import protocol
        raster = cube_web.blank_raster(25)
        self.assertEqual(cube_web.raster_lines(raster), protocol.feed_dots(25))
        self.assertFalse(any(raster))


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
