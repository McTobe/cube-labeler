#!/usr/bin/env python3
"""
Regression tests for the issues found in the October 2026 code audit.
"""

import io
import json
import os
import sys
import tempfile
import unittest
import urllib.request
from unittest import mock

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from PIL import Image

from core import secret_store
from core.ai_generator import GeminiProvider, ModelNotFoundError
from core.config import ConfigManager, DEFAULT_GEMINI_IMAGE_MODEL
from core.inventory_renderer import ComponentLabelConfig, FastenerLabelConfig
from core.label_renderer import LabelConfig, LabelRenderer
from core.ptstatus import StatusRegister, unpack_status
from core.specs import get_tape_spec, tape_width_from_status
from core.templates import export_config_to_json, load_config_from_json


def _status_bytes(status_type=0x00, err=0, tape_width=12, phase_type=0x00):
    reg = StatusRegister()
    reg.magic = b"\x80\x20B0"
    reg.model = 0x72
    reg.err = err
    reg.tape_width = tape_width
    reg.tape_type = 0x01
    reg.status_type = status_type
    reg.phase_type = phase_type
    reg.tape_bgcolor = 0x01
    reg.tape_fgcolor = 0x08
    return bytes(reg)


class TestTapeWidths(unittest.TestCase):
    def setUp(self):
        self.renderer = LabelRenderer()

    def test_3_5mm_tape_uses_its_own_spec(self):
        preview, _, _, _ = self.renderer.render(LabelConfig(text="Hi", tape_width_mm=3.5))
        self.assertEqual(preview.size[1], get_tape_spec(3.5)["canvas_height"])

    def test_unknown_width_raises(self):
        with self.assertRaises(ValueError):
            get_tape_spec(3)

    def test_status_width_mapping(self):
        self.assertEqual(tape_width_from_status(4), 3.5)
        self.assertEqual(tape_width_from_status(12), 12.0)

    def test_inventory_label_always_renders_at_12mm(self):
        cfg = LabelConfig(inventory_config=FastenerLabelConfig(), tape_width_mm=9)
        preview, _, raster, _ = self.renderer.render(cfg)
        self.assertEqual(preview.size[1], get_tape_spec(12)["canvas_height"])
        self.assertEqual(len(raster) % 16, 0)

    def test_fixed_font_overflow_warns(self):
        cfg = LabelConfig(text="Big", auto_fit_font=False, fixed_font_size=120)
        _, _, _, metrics = self.renderer.render(cfg)
        self.assertIsNotNone(metrics.warning)


class TestTemplates(unittest.TestCase):
    def _roundtrip(self, cfg):
        path = os.path.join(tempfile.mkdtemp(), "t.json")
        self.assertTrue(export_config_to_json(cfg, path))
        return load_config_from_json(path), path

    def test_fastener_roundtrip_renders(self):
        loaded, _ = self._roundtrip(LabelConfig(inventory_config=FastenerLabelConfig(thread_size="M5")))
        self.assertIsInstance(loaded.inventory_config, FastenerLabelConfig)
        self.assertEqual(loaded.inventory_config.thread_size, "M5")
        LabelRenderer().render(loaded)

    def test_component_roundtrip(self):
        loaded, _ = self._roundtrip(LabelConfig(inventory_config=ComponentLabelConfig(spec_primary="608ZZ")))
        self.assertIsInstance(loaded.inventory_config, ComponentLabelConfig)

    def test_unknown_keys_are_ignored(self):
        _, path = self._roundtrip(LabelConfig(text="X"))
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        data["some_future_setting"] = 1
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        self.assertEqual(load_config_from_json(path).text, "X")

    def test_legacy_file_without_type_tag(self):
        _, path = self._roundtrip(LabelConfig(inventory_config=FastenerLabelConfig()))
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        del data["inventory_type"]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        self.assertIsInstance(load_config_from_json(path).inventory_config, FastenerLabelConfig)

    def test_invalid_json_gives_message(self):
        path = os.path.join(tempfile.mkdtemp(), "bad.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write("{not json")
        with self.assertRaises(ValueError):
            load_config_from_json(path)


class TestStatusPacket(unittest.TestCase):
    def test_non_brother_packet_is_rejected(self):
        with self.assertRaises(ValueError):
            unpack_status(b"\x00" * 32)


class TestConfigAndAI(unittest.TestCase):
    def test_legacy_text_model_maps_to_image_model(self):
        cfg = ConfigManager.__new__(ConfigManager)
        cfg._config = {"gemini_model": "gemini-2.5-flash"}
        self.assertEqual(cfg.gemini_model, DEFAULT_GEMINI_IMAGE_MODEL)

    @unittest.skipUnless(secret_store.is_supported(), "DPAPI is Windows-only")
    def test_secret_store_roundtrip(self):
        token = secret_store.protect("abc123")
        self.assertIsNotNone(token)
        self.assertNotIn("abc123", token)
        self.assertEqual(secret_store.unprotect(token), "abc123")

    def test_api_key_sent_in_header_not_url(self):
        captured = {}

        class _Resp(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def fake_urlopen(req, timeout=None):
            captured["url"] = req.full_url
            captured["key"] = req.get_header("X-goog-api-key")
            return _Resp(b"{}")

        gen = GeminiProvider(api_key="SECRET_KEY")
        with mock.patch.object(urllib.request, "urlopen", fake_urlopen):
            gen._call_gemini_rest("some-model", {})
        self.assertNotIn("SECRET_KEY", captured["url"])
        self.assertEqual(captured["key"], "SECRET_KEY")

    def test_falls_back_only_on_missing_model(self):
        gen = GeminiProvider(api_key="K")
        calls = []

        def fake_call(model, payload):
            calls.append(model)
            if len(calls) == 1:
                raise ModelNotFoundError("gone")
            raise RuntimeError("Gemini API Error (500): boom")

        with mock.patch.object(gen, "_call_gemini_rest", fake_call):
            with self.assertRaisesRegex(RuntimeError, "500"):
                gen.redraw(Image.new("RGB", (8, 8), "white"), model="missing-model")
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0], "missing-model")


if __name__ == "__main__":
    unittest.main()
