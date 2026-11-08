#!/usr/bin/env python3
"""
Tests for the user's own templates: saving into the app's data folder, safe file names,
listing and deleting, and the My templates list on the Templates page.
"""

import os
import shutil
import sys
import tempfile
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from core.label_renderer import LabelConfig
from core import templates as tp


class TestUserTemplates(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.folder, True)

    def test_save_list_open_and_delete(self):
        cfg = LabelConfig(text="Shelf 3")
        path = tp.save_user_template(cfg, "Shelf labels", self.folder)
        self.assertEqual(os.path.basename(path), "Shelf labels.json")
        self.assertEqual(tp.list_user_templates(self.folder), [("Shelf labels", path)])
        self.assertEqual(tp.load_config_from_json(path).text, "Shelf 3")
        # Saving under the same name replaces it
        tp.save_user_template(LabelConfig(text="Shelf 4"), "Shelf labels", self.folder)
        self.assertEqual(len(tp.list_user_templates(self.folder)), 1)
        self.assertEqual(tp.load_config_from_json(path).text, "Shelf 4")
        self.assertTrue(tp.delete_user_template(path))
        self.assertEqual(tp.list_user_templates(self.folder), [])

    def test_old_templates_get_the_apps_cut_lines(self):
        cfg = tp.config_from_dict({"text": "Old", "cut_line": False, "auto_cut_hardware": True})
        self.assertTrue(cfg.cut_line)
        self.assertFalse(cfg.auto_cut_hardware)

    def test_names_windows_cannot_store(self):
        self.assertEqual(tp.template_file_name('M3: 10/20 "bolts"?'), "M3_ 10_20 _bolts__.json")
        self.assertEqual(tp.template_file_name("  ...  "), "My template.json")
        self.assertEqual(tp.template_file_name("a" * 200), "a" * 80 + ".json")


if __name__ == "__main__":
    unittest.main()
