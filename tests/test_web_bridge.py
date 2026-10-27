#!/usr/bin/env python3
"""
Tests for web/cube_web.py, the Python side of the web app. It runs in Pyodide in the browser,
but it is plain Python, so CPython checks it here against the desktop printer driver.
"""

import base64
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
        shipped = [os.path.join(core_dir, n) for n in build.CORE_MODULES]
        shipped += [os.path.join(BASE_DIR, "ui", n) for n in build.UI_MODULES]
        for path in shipped:
            name = os.path.basename(path)
            with open(path, encoding="utf-8") as f:
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


class TestWebBinLabelsAndQueue(unittest.TestCase):
    def test_bin_label_matches_desktop_renderer(self):
        from core.inventory_renderer import FastenerLabelConfig
        fastener = cube_web.bin_defaults("en")["fastener"]
        result = cube_web.render_label({"bin": fastener, "tape_width_mm": 6.0})
        fields = {k: v for k, v in fastener.items() if k != "kind"}
        _, _, raster, _ = LabelRenderer().render(
            LabelConfig(inventory_config=FastenerLabelConfig(**fields), tape_width_mm=12.0)
        )
        self.assertEqual(result["raster"], raster)

    def test_part_label_with_own_icon(self):
        part = dict(cube_web.bin_defaults("en")["component"], icon_type="custom")
        picture = Image.new("RGB", (30, 30), "white")
        picture.paste((0, 0, 0), (5, 5, 25, 25))
        data = io.BytesIO()
        picture.save(data, format="PNG")
        with_icon = cube_web.render_label({"bin": dict(part, icon_data=data.getvalue())})
        # Without the picture bytes, a custom icon falls back to no icon instead of failing
        without = cube_web.render_label({"bin": part})
        self.assertNotEqual(with_icon["raster"], without["raster"])

    def test_bin_icon_paths_from_the_page_are_ignored(self):
        part = dict(cube_web.bin_defaults("en")["component"], icon_type="custom", custom_icon_path="/etc/passwd")
        self.assertGreater(cube_web.render_label({"bin": part})["metrics"]["raster_lines"], 0)

    def test_queue_prints_as_one_strip(self):
        labels = [{"text": "One"}, {"bin": cube_web.bin_defaults("en")["component"]}, {"text": "Three"}]
        result = cube_web.render_queue(labels)
        self.assertEqual(result["metrics"]["label_count"], 3)
        self.assertEqual(result["metrics"]["tape_saved_mm"], 50.0)
        configs = [cube_web._label_config(label) for label in labels]
        self.assertEqual(result["raster"], LabelRenderer().render_batch(configs)[2])

    def test_queue_copies_repeat_a_label_and_spans_point_at_each(self):
        labels = [{"text": "One"}, {"text": "Two"}]
        result = cube_web.render_queue(labels, [3, 1])
        self.assertEqual(result["metrics"]["label_count"], 4)
        configs = [cube_web._label_config(labels[0])] * 3 + [cube_web._label_config(labels[1])]
        self.assertEqual(result["raster"], LabelRenderer().render_batch(configs)[2])
        spans = result["spans"]
        self.assertEqual(len(spans), 4)
        # In order, apart, and inside the strip
        for (s0, e0), (s1, e1) in zip(spans, spans[1:]):
            self.assertLess(s0, e0)
            self.assertLess(e0, s1)
        self.assertGreater(spans[0][0], 0)
        self.assertLess(spans[-1][1], 1)
        self.assertEqual(cube_web.render_queue([{"text": "Solo"}])["spans"], [[0.0, 1.0]])

    def test_bin_defaults_and_suggestions_follow_the_language(self):
        self.assertEqual(cube_web.bin_defaults("sv")["fastener"]["category"], "SKRUV")
        self.assertIn("KULLAGER", cube_web.bin_name_suggestions("sv")["component"])
        self.assertIn(["sv", "Svenska"], cube_web.label_languages())

    def test_thumbnail_height(self):
        png = cube_web.label_thumbnail({"text": "Hello"}, 40)
        self.assertEqual(Image.open(io.BytesIO(png)).height, 40)


class TestWebIcons(unittest.TestCase):
    def _picture(self):
        picture = Image.new("RGB", (200, 120), "white")
        picture.paste((0, 0, 0), (40, 20, 160, 100))
        data = io.BytesIO()
        picture.save(data, format="JPEG")
        return data.getvalue()

    def test_library_lists_every_icon_with_its_file(self):
        import json
        import tempfile
        from unittest import mock
        import build
        with tempfile.TemporaryDirectory() as dist, mock.patch.object(build, "DIST_DIR", dist):
            build.build_icon_library()
            with open(os.path.join(dist, "icons", "library.json"), encoding="utf-8") as f:
                data = json.load(f)
            self.assertGreater(len(data["icons"]), 100)
            for icon in data["icons"]:
                self.assertIn(icon["category"], data["categories"])
                self.assertTrue(os.path.isfile(os.path.join(dist, icon["file"])), icon["file"])
                self.assertEqual(icon["file"], "icons/" + icon["key"])

    def test_print_preview_is_the_bin_label_size(self):
        preview = Image.open(io.BytesIO(cube_web.icon_print_preview(self._picture())))
        self.assertEqual(max(preview.size), 56)

    def test_editor_matches_the_desktop_editor(self):
        from core import icon_editor as ie
        original = cube_web.prepare_icon_original(self._picture())
        edit = {"mode": "outline", "thickness": 1, "rotate": 1}
        touch = bytearray(ie.TOUCH_GRID * ie.TOUCH_GRID)
        touch[0] = ie.TOUCH_INK
        result = cube_web.edit_icon(original, edit, bytes(touch))
        source = Image.open(io.BytesIO(original)).convert("RGBA")
        layer = Image.frombytes("L", (ie.TOUCH_GRID, ie.TOUCH_GRID), bytes(touch))
        expected = ie.render_icon(source, ie.IconEdit.from_dict(edit), layer)
        self.assertEqual(Image.open(io.BytesIO(result["icon_png"])).convert("RGBA").tobytes(), expected.tobytes())
        self.assertTrue(result["has_ink"])
        self.assertEqual(result["edit"]["mode"], "outline")
        # Turned a quarter, the 200 x 120 picture stands up
        view = Image.open(io.BytesIO(result["view_png"]))
        self.assertGreater(view.height, view.width)
        self.assertEqual(max(Image.open(io.BytesIO(result["print_png"])).size), ie.PRINT_DOTS)

    def test_touch_ups_from_a_desktop_backup(self):
        from core import icon_editor as ie
        layer = ie.new_touch_layer()
        layer.putpixel((3, 4), ie.TOUCH_ERASE)
        cells = cube_web.touch_cells(cube_web._png(layer))
        self.assertEqual(cells[4 * ie.TOUCH_GRID + 3], ie.TOUCH_ERASE)
        self.assertEqual(cube_web.touch_cells(cube_web.touch_png(cells)), cells)

    def test_blank_picture_has_no_ink(self):
        data = io.BytesIO()
        Image.new("RGB", (50, 50), "white").save(data, format="PNG")
        result = cube_web.edit_icon(cube_web.prepare_icon_original(data.getvalue()))
        self.assertFalse(result["has_ink"])
        self.assertIsNone(result["print_png"])


class TestWebTemplatesAndBackups(unittest.TestCase):
    def _png(self, color="black"):
        data = io.BytesIO()
        Image.new("RGBA", (8, 8), color).save(data, format="PNG")
        return data.getvalue()

    def test_desktop_template_opens_in_the_web_version(self):
        import json
        from ui.templates import BUILTIN_PRESETS
        item = cube_web.template_from_desktop(json.dumps(BUILTIN_PRESETS["Storage Box"]["config"]))
        self.assertEqual(item["mode"], "text")
        self.assertEqual(item["label"]["text"], "ELECTRONICS & CORDS\nShelf 2 - Row B")
        self.assertIn(item["label"]["font_name"], cube_web.font_names())

    def test_starting_points_and_bin_labels_use_shipped_fonts(self):
        from unittest import mock
        from core.font_manager import FontManager
        from ui.templates import BUILTIN_PRESETS, WEB_PRESETS
        with mock.patch("core.font_manager.system_font_dirs", return_value=[]), \
                mock.patch("core.font_manager.sys.platform", "linux"):
            shipped = FontManager()
        shipped.scan_font_dir(os.path.join(BASE_DIR, "web", "fonts"))
        names = shipped.get_font_names()
        self.assertIn(cube_web.WEB_BIN_FONT, names)
        for family in cube_web.WEB_FONT_SUBSTITUTES.values():
            self.assertIn(family, names)
            self.assertIn(family + " Bold", names)
        with mock.patch.object(cube_web, "font_names", return_value=names):
            self.assertEqual(cube_web._web_font("Consolas Bold"), "JetBrains Mono Bold")
            self.assertEqual(cube_web._web_font("Segoe UI"), "Inter")
            self.assertEqual(cube_web._web_font("Arial Bold"), "Arimo Bold")
            self.assertEqual(cube_web._web_font("Calibri"), "Arimo")
            presets = cube_web.template_presets()
        self.assertEqual(len(presets), len(BUILTIN_PRESETS) + len(WEB_PRESETS))
        for preset in presets:
            self.assertIn(preset["label"]["font_name"], names, preset["key"])
        for preset in WEB_PRESETS.values():
            self.assertIn(preset["config"]["font_name"], names)

    def test_web_template_opens_on_the_desktop(self):
        import json
        from ui.templates import config_from_dict
        text = {"mode": "text", "label": {"text": "Box 4", "qr_enabled": True, "qr_data": "x",
                                         "image": {"name": "a.png", "data": self._png()}}}
        saved = cube_web.template_to_desktop(text)
        cfg = config_from_dict(json.loads(saved))
        self.assertEqual(cfg.text, "Box 4")
        self.assertIsNone(cfg.image_path)
        again = cube_web.template_from_desktop(saved)
        self.assertEqual(again["label"]["image"]["data"], self._png())
        part = dict(cube_web.bin_defaults("en")["component"], icon_type="custom", icon={"name": "i.png", "data": self._png()})
        cfg = config_from_dict(json.loads(cube_web.template_to_desktop({"mode": "bin", "bin": part})))
        self.assertIsNone(cfg.inventory_config.custom_icon_path)
        back = cube_web.template_from_desktop(cube_web.template_to_desktop({"mode": "bin", "bin": part}))
        self.assertEqual(back["bin"]["icon_type"], "custom")
        self.assertEqual(back["bin"]["kind"], "component")

    def test_broken_template_is_refused(self):
        with self.assertRaisesRegex(ValueError, "not a template"):
            cube_web.template_from_desktop("{nope")

    def test_web_backup_restores_on_the_desktop(self):
        from core import backup
        cells = bytearray(64 * 64)
        cells[5] = 1
        data = cube_web.make_backup({
            "created": "2026-10-24T20:00:00+02:00",
            "icons": [{"file": "washer.png", "favourite": True, "icon": self._png(),
                       "meta": {"title": "Washer", "category": "My Icons", "keywords": ["ring"], "edit": {"mode": "outline"}},
                       "original": self._png("white"), "touch": bytes(cells)}],
            "settings": {"label_language": "sv", "gemini_api_key": "secret", "icon_favourites": ["user/washer.png"]},
            "templates": [{"name": "Shelf A", "json": cube_web.template_to_desktop({"mode": "text", "label": {"text": "A"}})}],
        })
        read = backup.read_backup(io.BytesIO(data))
        self.assertEqual(read.icons[0].title, "Washer")
        self.assertTrue(read.icons[0].favourite)
        self.assertIsNotNone(read.icons[0].touch)
        self.assertNotIn("gemini_api_key", read.settings)
        self.assertEqual(list(read.templates), ["templates/Shelf A.json"])

    def test_added_fonts_travel_between_web_and_desktop(self):
        from core import backup
        with open(os.path.join(BASE_DIR, "tests", "fonts", "Roboto-Regular.ttf"), "rb") as f:
            font = f.read()
        contents = {"created": "", "icons": [], "settings": {}, "templates": [],
                    "fonts": [{"filename": "Roboto-Regular.ttf", "data": font}, {"filename": "../evil.ttf", "data": b"x"}]}
        data = cube_web.make_backup(contents)
        read = backup.read_backup(io.BytesIO(data))
        self.assertEqual(read.fonts, {"fonts/Roboto-Regular.ttf": font})
        self.assertIn(backup.FONTS, read.parts)
        opened = cube_web.open_backup(data)
        self.assertEqual(opened["fonts"], [{"filename": "Roboto-Regular.ttf", "data": font}])
        # A desktop backup with an added font opens in the web version too
        buf = io.BytesIO()
        backup.write_backup(backup.Backup(created="", icons=[], settings={}, files={"fonts/Roboto-Regular.ttf": font}), buf)
        self.assertEqual(cube_web.open_backup(buf.getvalue())["fonts"][0]["filename"], "Roboto-Regular.ttf")
        self.assertNotEqual(cube_web.backup_digest(contents), cube_web.backup_digest(dict(contents, fonts=[])))

    def test_backup_digest_ignores_time_and_recent_icons(self):
        contents = {
            "created": "2026-10-24T20:00:00+02:00",
            "icons": [{"file": "washer.png", "favourite": False, "icon": self._png(), "meta": {"title": "Washer"}}],
            "settings": {"label_language": "sv", "icon_recent": ["user/washer.png"]},
            "templates": [],
        }
        first = cube_web.backup_digest(contents)
        later = dict(contents, created="2026-10-25T08:00:00+02:00", settings={"label_language": "sv", "icon_recent": []})
        self.assertEqual(cube_web.backup_digest(later), first)
        changed = dict(contents, icons=[dict(contents["icons"][0], icon=self._png("red"))])
        self.assertNotEqual(cube_web.backup_digest(changed), first)
        self.assertNotEqual(cube_web.backup_digest(dict(contents, settings={"label_language": "en"})), first)

    def test_backup_digest_reads_desktop_numbers_like_the_page(self):
        import json
        contents = {"created": "", "icons": [], "settings": {}, "templates": [{"name": "A", "json": json.dumps({"font_scale": 100.0})}]}
        same = dict(contents, templates=[{"name": "A", "json": json.dumps({"font_scale": 100}, indent=2)}])
        self.assertEqual(cube_web.backup_digest(contents), cube_web.backup_digest(same))

    def test_desktop_backup_opens_in_the_web_version(self):
        from core import backup
        layer = Image.new("L", (64, 64), 0)
        layer.putpixel((1, 0), 2)
        touch = io.BytesIO()
        layer.save(touch, format="PNG")
        made = backup.Backup(
            created="2026-10-24T20:00:00+02:00",
            icons=[backup.BackupIcon(file="nut.png", meta={"title": "Nut", "edit": {"mode": "drawing"}}, favourite=False,
                                     icon=self._png(), original=self._png("white"), touch=touch.getvalue())],
            settings={"label_language": "de"},
            files={"templates/Bin.json": cube_web.template_to_desktop(
                {"mode": "bin", "bin": cube_web.bin_defaults("en")["fastener"]}).encode(), "templates/Bad.json": b"{"},
        )
        out = io.BytesIO()
        backup.write_backup(made, out)
        opened = cube_web.open_backup(out.getvalue())
        self.assertEqual(opened["icons"][0]["meta"]["title"], "Nut")
        self.assertEqual(opened["icons"][0]["touch"][1], 2)
        self.assertEqual(opened["settings"]["label_language"], "de")
        self.assertEqual([t["name"] for t in opened["templates"]], ["Bin"])
        self.assertEqual(opened["skipped_templates"], ["Bad"])

    def test_not_a_backup(self):
        with self.assertRaisesRegex(ValueError, "not a Cube Labeler backup"):
            cube_web.open_backup(b"hello")


class TestWebAiIcons(unittest.TestCase):
    def _picture(self):
        data = io.BytesIO()
        Image.new("RGB", (40, 30), "white").save(data, format="PNG")
        return data.getvalue()

    def _desktop_request(self, service, model):
        import json
        import urllib.request
        from unittest import mock
        from core import ai_generator as ag
        sent = {}

        class Answer:
            def __init__(self, body):
                self.body = body

            def read(self):
                return self.body

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        png = base64.b64encode(self._picture()).decode()
        answer = ({"candidates": [{"content": {"parts": [{"inlineData": {"data": png}}]}}]}
                  if service == "gemini" else {"data": [{"b64_json": png}]})

        def urlopen(req, timeout=None):
            sent.update(url=req.full_url, body=req.data, headers={k.lower(): v for k, v in req.header_items()})
            return Answer(json.dumps(answer).encode())

        provider = ag.PROVIDERS[service].__class__(api_key="K")
        with mock.patch.object(urllib.request, "urlopen", urlopen), mock.patch.object(ag.uuid, "uuid4") as uid:
            uid.return_value.hex = "fixed"
            provider.redraw(Image.open(io.BytesIO(self._picture())), model=model)
        return sent, answer

    def test_requests_match_the_desktop_app(self):
        from unittest import mock
        from core import ai_generator as ag
        from core.ai_generator import DEFAULT_PRESET
        for service in ("gemini", "openai", "openrouter"):
            with self.subTest(service=service):
                sent, answer = self._desktop_request(service, "m1")
                with mock.patch.object(ag.uuid, "uuid4") as uid:
                    uid.return_value.hex = "fixed"
                    req = cube_web.ai_request(service, self._picture(), DEFAULT_PRESET, "", "m1")
                self.assertEqual(req["url"], sent["url"])
                self.assertEqual(req["body"], sent["body"])
                self.assertEqual(sent["headers"][req["key_header"].lower()], req["key_prefix"] + "K")
                import json
                result = cube_web.ai_answer(service, "m1", 200, json.dumps(answer))
                self.assertEqual(Image.open(io.BytesIO(result["png"])).size, (40, 30))

    def test_answers_with_errors(self):
        missing = cube_web.ai_answer("openai", "m", 404, '{"error": {"message": "nope"}}')
        self.assertTrue(missing["try_next_model"])
        quota = cube_web.ai_answer("gemini", "m", 429, '{"error": {"message": "quota"}}')
        self.assertIn("gemini.google.com", quota["error"])
        self.assertFalse(quota["try_next_model"])
        self.assertIn("text instead of a picture",
                      cube_web.ai_answer("gemini", "m", 200, '{"candidates": [{"content": {"parts": [{"text": "hi"}]}}]}')["error"])
        self.assertIn("cannot read", cube_web.ai_answer("openai", "m", 200, "<html>")["error"])

    def test_models_and_custom_instructions(self):
        self.assertEqual(cube_web.ai_models("openai")[0], "gpt-image-2")
        self.assertEqual(cube_web.ai_models("openai", "mine")[:2], ["mine", "gpt-image-1.5"])
        services = cube_web.ai_services()
        self.assertEqual([s["id"] for s in services["services"]], ["gemini", "openai", "openrouter"])
        with self.assertRaisesRegex(ValueError, "Custom"):
            cube_web.ai_request("openai", self._picture(), services["custom"], "  ", "m")


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
