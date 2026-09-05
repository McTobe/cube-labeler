#!/usr/bin/env python3
"""
Unit tests for Icon Library, Config Manager, and AI Wireframe Generator.
"""

import os
import sys
import unittest
from PIL import Image, ImageDraw

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import ConfigManager
from core.icon_manager import IconManager, IconItem
from core.ai_generator import (
    post_process_thermal,
    local_edge_filter,
    GeminiWireframeGenerator,
    THERMAL_WIREFRAME_SYSTEM_PROMPT,
)


class TestConfigManager(unittest.TestCase):
    def test_config_defaults_and_keys(self):
        cfg = ConfigManager()
        self.assertIn("gemini_api_key", cfg._config)
        self.assertIn("gemini_model", cfg._config)
        self.assertIn("last_serial_port", cfg._config)
        user_dir = cfg.user_icons_dir
        self.assertTrue(os.path.isdir(user_dir))
        self.assertEqual(user_dir, os.path.normpath(user_dir))

    def test_open_custom_folder_logic(self):
        from unittest.mock import patch
        from ui.icon_browser import IconBrowserDialog

        # Test that _open_custom_folder calls os.startfile on Windows without NameError or crash
        with patch("os.startfile") as mock_startfile:
            # We can create a dummy mock object with _open_custom_folder
            dummy = object.__new__(IconBrowserDialog)
            dummy._open_custom_folder()
            if sys.platform == "win32":
                mock_startfile.assert_called_once()


class TestIconManager(unittest.TestCase):
    def setUp(self):
        self.mgr = IconManager()

    def test_bundled_icons_discovered(self):
        icons = self.mgr.list_icons()
        self.assertGreaterEqual(len(icons), 25, "Expected at least 25 built-in icons")

    def test_categories(self):
        cats = self.mgr.CATEGORIES
        self.assertIn("Fasteners", cats)
        self.assertIn("Engineering", cats)
        self.assertIn("Electronics", cats)
        self.assertIn("Tools", cats)
        self.assertIn("Symbols", cats)
        self.assertIn("My Icons", cats)

        fasteners = self.mgr.list_icons(category="Fasteners")
        self.assertGreater(len(fasteners), 5)

        engineering = self.mgr.list_icons(category="Engineering")
        self.assertGreaterEqual(len(engineering), 3)

        electronics = self.mgr.list_icons(category="Electronics")
        self.assertGreater(len(electronics), 5)

    def test_search_bearing_and_torx(self):
        bearing_results = self.mgr.list_icons(search_query="bearing")
        self.assertGreaterEqual(len(bearing_results), 1)
        self.assertTrue(any("bearing" in item.id.lower() for item in bearing_results))

        torx_results = self.mgr.list_icons(search_query="torx")
        self.assertGreaterEqual(len(torx_results), 1)
        self.assertTrue(any("torx" in item.id.lower() for item in torx_results))

    def test_save_user_icon(self):
        test_img = Image.new("RGBA", (100, 100), (0, 0, 0, 255))
        item = self.mgr.save_user_icon(test_img, "unit_test_save_icon")
        self.assertIsNotNone(item)
        self.assertTrue(os.path.isfile(item.file_path))
        # Cleanup
        try:
            os.remove(item.file_path)
            self.mgr.reload()
        except Exception:
            pass


class TestAIGenerator(unittest.TestCase):
    def test_post_process_thermal(self):
        # Create image with thin line in center of white background
        img = Image.new("RGB", (200, 200), "white")
        draw = ImageDraw.Draw(img)
        draw.line([(20, 20), (180, 180)], fill="black", width=2)

        normal = post_process_thermal(img, target_size=(128, 128), line_thickness=1)
        bold = post_process_thermal(img, target_size=(128, 128), line_thickness=2)
        extra_bold = post_process_thermal(img, target_size=(128, 128), line_thickness=3)

        self.assertEqual(normal.size, (128, 128))
        self.assertEqual(bold.size, (128, 128))
        self.assertEqual(normal.mode, "RGBA")

        # Count solid black pixels (alpha == 255)
        normal_black = sum(1 for a in normal.split()[3].get_flattened_data() if a == 255)
        bold_black = sum(1 for a in bold.split()[3].get_flattened_data() if a == 255)
        extra_bold_black = sum(1 for a in extra_bold.split()[3].get_flattened_data() if a == 255)

        self.assertGreater(bold_black, normal_black, "Bold should have more stroke pixels than normal")
        self.assertGreater(extra_bold_black, bold_black, "Extra bold should have more stroke pixels than bold")

        # Test explicit color inversion
        inverted = post_process_thermal(img, target_size=(128, 128), line_thickness=1, invert=True)
        self.assertEqual(inverted.size, (128, 128))
        self.assertEqual(inverted.mode, "RGBA")

    def test_local_edge_filter(self):
        # Create image with shapes
        img = Image.new("RGB", (150, 150), "white")
        draw = ImageDraw.Draw(img)
        draw.ellipse([30, 30, 120, 120], fill="gray")

        # Test with line_thickness parameter (which caused previous crash)
        edge_img = local_edge_filter(img, sensitivity=120, line_weight=2, line_thickness=1)
        self.assertEqual(edge_img.size, (256, 256))
        self.assertEqual(edge_img.mode, "RGBA")

    def test_gemini_prompt_and_client(self):
        gen = GeminiWireframeGenerator(api_key="TEST_KEY")
        self.assertEqual(gen.api_key, "TEST_KEY")
        self.assertIn("BOLD & THICK LINEWORK", THERMAL_WIREFRAME_SYSTEM_PROMPT)
        self.assertIn("AGGRESSIVE SIMPLIFICATION & ABSTRACTION", THERMAL_WIREFRAME_SYSTEM_PROMPT)
        self.assertIn("thermal label", THERMAL_WIREFRAME_SYSTEM_PROMPT.lower())


if __name__ == "__main__":
    unittest.main()
