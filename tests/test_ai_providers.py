#!/usr/bin/env python3
"""
Tests for redrawing pictures with AI services: presets, the Custom preset and the
requests sent to Gemini, OpenAI and OpenRouter (no network: urlopen is faked).
"""

import base64
import io
import json
import os
import sys
import unittest
import urllib.error
import urllib.request
from unittest import mock

from PIL import Image

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from core import ai_generator as ag
from core.config import ConfigManager
from core.icon_editor import DRAWING


def png_b64(colour="black") -> str:
    buf = io.BytesIO()
    Image.new("RGB", (16, 16), colour).save(buf, "PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeConfig:
    def __init__(self, provider="gemini"):
        self.data = {"ai_provider": provider}

    @property
    def ai_provider(self):
        return self.data["ai_provider"]

    def api_key(self, provider):
        return self.data.get(f"{provider}_key", "")

    def ai_model(self, provider):
        return self.data.get(f"{provider}_model", "")

    @property
    def gemini_model(self):
        return self.ai_model("gemini") or ag.DEFAULT_GEMINI_IMAGE_MODEL


class TestPresets(unittest.TestCase):
    def test_labels_and_modes(self):
        self.assertEqual(ag.PRESET_LABELS[0], ag.DEFAULT_PRESET)
        self.assertEqual(ag.PRESET_LABELS[-1], ag.CUSTOM)
        self.assertEqual(ag.preset_mode(ag.DEFAULT_PRESET), DRAWING)
        self.assertEqual(ag.preset_mode("Bold line drawing"), DRAWING)
        self.assertEqual(ag.preset_mode(ag.CUSTOM), DRAWING)

    def test_prompt_keeps_the_print_rules(self):
        for label in ag.PRESET_LABELS[:-1]:
            prompt = ag.build_prompt(label)
            self.assertIn("BOLD & THICK LINEWORK", prompt)
            self.assertIn("attached picture", prompt)

    def test_custom_uses_the_users_words(self):
        prompt = ag.build_prompt(ag.CUSTOM, "front view, keep both screw holes")
        self.assertIn("STYLE: front view, keep both screw holes", prompt)
        self.assertIn("BOLD & THICK LINEWORK", prompt)
        with self.assertRaises(ValueError):
            ag.build_prompt(ag.CUSTOM, "   ")


class ProviderTestCase(unittest.TestCase):
    def setUp(self):
        self.config = FakeConfig()
        patcher = mock.patch.object(ag, "config_manager", self.config)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.picture = Image.new("RGBA", (2000, 1000), (200, 0, 0, 255))
        self.requests = []

    def fake_urlopen(self, *responses):
        responses = list(responses)

        def urlopen(req, timeout=None):
            self.requests.append(req)
            res = responses.pop(0)
            if isinstance(res, Exception):
                raise res
            return _Resp(json.dumps(res).encode("utf-8"))

        return mock.patch.object(urllib.request, "urlopen", urlopen)

    @staticmethod
    def http_error(code, body):
        return urllib.error.HTTPError("https://x", code, "err", {}, io.BytesIO(json.dumps(body).encode("utf-8")))


class TestProviders(ProviderTestCase):
    def test_registry_and_choice(self):
        self.assertEqual(list(ag.PROVIDERS), ["gemini", "openai", "openrouter"])
        self.assertEqual(ag.current_provider().id, "gemini")
        self.config.data["ai_provider"] = "openrouter"
        self.assertEqual(ag.current_provider().id, "openrouter")
        self.config.data["ai_provider"] = "nonsense"
        self.assertEqual(ag.current_provider().id, "gemini")
        self.assertEqual(ag.provider_by_name("OpenAI").id, "openai")

    def test_no_key(self):
        with self.assertRaisesRegex(ValueError, "API key"):
            ag.OpenAIProvider().redraw(self.picture)

    def test_gemini_request(self):
        gem = ag.GeminiProvider(api_key="G")
        res = {"candidates": [{"content": {"parts": [{"inlineData": {"data": png_b64()}}]}}]}
        with self.fake_urlopen(res):
            out = gem.redraw(self.picture, "Bold line drawing")
        self.assertEqual(out.size, (16, 16))
        req = self.requests[0]
        self.assertIn(ag.DEFAULT_GEMINI_IMAGE_MODEL, req.full_url)
        self.assertEqual(req.get_header("X-goog-api-key"), "G")
        body = json.loads(req.data)
        self.assertIn("BOLD BLACK LINE DRAWING", body["contents"][0]["parts"][0]["text"])
        sent = Image.open(io.BytesIO(base64.b64decode(body["contents"][0]["parts"][1]["inline_data"]["data"])))
        self.assertEqual(sent.size, (1024, 512))

    def test_openai_request(self):
        oa = ag.OpenAIProvider(api_key="O")
        with self.fake_urlopen({"data": [{"b64_json": png_b64()}]}):
            out = oa.redraw(self.picture, ag.CUSTOM, "make it round")
        self.assertEqual(out.size, (16, 16))
        req = self.requests[0]
        self.assertEqual(req.full_url, "https://api.openai.com/v1/images/edits")
        self.assertEqual(req.get_header("Authorization"), "Bearer O")
        self.assertIn("multipart/form-data; boundary=", req.get_header("Content-type"))
        self.assertIn(b'name="model"\r\n\r\ngpt-image-2\r\n', req.data)
        self.assertIn(b"STYLE: make it round", req.data)
        self.assertIn(b'name="image[]"; filename="picture.png"', req.data)
        self.assertIn(b"\x89PNG", req.data)

    def test_openai_falls_back_only_on_missing_model(self):
        oa = ag.OpenAIProvider(api_key="O")
        missing = self.http_error(404, {"error": {"message": "The model does not exist", "code": "model_not_found"}})
        with self.fake_urlopen(missing, {"data": [{"b64_json": png_b64()}]}):
            oa.redraw(self.picture)
        self.assertIn(b"gpt-image-1.5", self.requests[1].data)

        self.requests.clear()
        with self.fake_urlopen(self.http_error(400, {"error": {"message": "bad picture"}})):
            with self.assertRaisesRegex(RuntimeError, "bad picture"):
                oa.redraw(self.picture)
        self.assertEqual(len(self.requests), 1)

    def test_openrouter_request_and_chosen_model(self):
        self.config.data["openrouter_model"] = "openai/gpt-image-2"
        orr = ag.OpenRouterProvider(api_key="R")
        with self.fake_urlopen({"data": [{"b64_json": png_b64(), "media_type": "image/png"}]}):
            orr.redraw(self.picture)
        req = self.requests[0]
        self.assertEqual(req.full_url, "https://openrouter.ai/api/v1/images")
        self.assertEqual(req.get_header("Authorization"), "Bearer R")
        body = json.loads(req.data)
        self.assertEqual(body["model"], "openai/gpt-image-2")
        self.assertTrue(body["input_references"][0]["image_url"]["url"].startswith("data:image/png;base64,"))

    def test_empty_answer(self):
        with self.fake_urlopen({"data": []}):
            with self.assertRaisesRegex(RuntimeError, "No picture"):
                ag.OpenRouterProvider(api_key="R").redraw(self.picture)


class TestConfigKeys(unittest.TestCase):
    def test_keys_and_models_per_service(self):
        cfg = ConfigManager.__new__(ConfigManager)
        cfg._config = {}
        cfg.save = lambda: None
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
            cfg.set_api_key("openai", "sk-1")
            cfg.set_api_key("gemini", "g-1")
            self.assertEqual(cfg.api_key("openai"), "sk-1")
            self.assertEqual(cfg.gemini_api_key, "g-1")
            self.assertEqual(cfg.api_key("openrouter"), "")
        cfg.set_ai_model("openrouter", " openai/gpt-image-2 ")
        self.assertEqual(cfg.ai_model("openrouter"), "openai/gpt-image-2")
        self.assertEqual(cfg.ai_provider, "gemini")
        cfg.ai_provider = "openai"
        self.assertEqual(cfg.ai_provider, "openai")
        with mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "from-env"}):
            self.assertEqual(cfg.api_key("openrouter"), "from-env")


if __name__ == "__main__":
    unittest.main()
