#!/usr/bin/env python3
"""
Tests for the language of hardware label text (core/label_language.py).
"""

import os
import sys
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from core.inventory_renderer import (
    ComponentLabelConfig,
    FastenerLabelConfig,
    InventoryRenderer,
)
from core.label_language import (
    LANGUAGES,
    TERMS,
    build_presets,
    component_categories,
    fastener_categories,
    normalize_language,
    term,
)


class TestLabelLanguage(unittest.TestCase):
    def test_every_term_has_every_language(self):
        for key, translations in TERMS.items():
            self.assertEqual(set(translations), set(LANGUAGES), key)

    def test_presets_render_in_every_language(self):
        renderer = InventoryRenderer()
        for lang in LANGUAGES:
            presets = build_presets(lang)
            self.assertEqual(list(presets), ["A1", "A2", "A3", "A4", "A5", "B1", "B2", "B3"])
            for preset in presets.values():
                if isinstance(preset.config, FastenerLabelConfig):
                    img = renderer.render_fastener(preset.config)
                else:
                    img = renderer.render_component(preset.config)
                self.assertEqual(img.size[1], 64, f"{lang} {preset.preset_id}")

    def test_preset_names_stay_english(self):
        self.assertEqual(
            [p.name for p in build_presets("en").values()],
            [p.name for p in build_presets("sv").values()],
        )

    def test_english_and_swedish_label_text(self):
        self.assertEqual(build_presets("en")["B1"].config.category_banner, "BEARINGS")
        self.assertEqual(build_presets("sv")["B1"].config.category_banner, "KULLAGER")
        self.assertEqual(build_presets("sv")["A4"].config.assortment_line1, "Blandade")
        self.assertEqual(fastener_categories("en")[0], "SCREWS")
        self.assertEqual(component_categories("sv")[0], "KULLAGER")

    def test_dataclass_defaults_are_english(self):
        self.assertEqual(FastenerLabelConfig().category, "SCREWS")
        self.assertEqual(FastenerLabelConfig().assortment_line1, "Mixed")
        self.assertEqual(ComponentLabelConfig().category_banner, "BEARINGS")

    def test_unknown_language_falls_back_to_english(self):
        self.assertEqual(normalize_language("de"), "en")
        self.assertEqual(term("nuts", "de"), "NUTS")


if __name__ == "__main__":
    unittest.main()
