#!/usr/bin/env python3
"""
Tests for the user's own templates: saving into the app's data folder, safe file names,
listing and deleting, and the My templates list on the Templates page.
"""

import importlib.util
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from core.label_renderer import LabelConfig
from ui import templates as tp


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

    def test_names_windows_cannot_store(self):
        self.assertEqual(tp.template_file_name('M3: 10/20 "bolts"?'), "M3_ 10_20 _bolts__.json")
        self.assertEqual(tp.template_file_name("  ...  "), "My template.json")
        self.assertEqual(tp.template_file_name("a" * 200), "a" * 80 + ".json")


@unittest.skipIf(importlib.util.find_spec("tkinter") is None, "tkinter is not installed")
class TestTemplatesView(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import customtkinter as ctk

        try:
            cls.root = ctk.CTk()
        except Exception as e:
            raise unittest.SkipTest(f"no display: {e}")
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def test_my_templates_list(self):
        from ui.templates_view import TemplatesView

        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder, True)
        opened = []
        view = TemplatesView(self.root, on_apply=lambda k: None, on_save=lambda: None, on_open=lambda: None,
                             on_open_user=opened.append, templates_folder=folder)
        self.addCleanup(view.destroy)
        self.assertEqual(view.user_rows, {})
        path = tp.save_user_template(LabelConfig(text="x"), "Drawer", folder)
        view.refresh_user_templates()
        self.assertEqual(list(view.user_rows), ["Drawer"])
        buttons = {w.cget("text"): w for w in view.user_rows["Drawer"].winfo_children()
                   if hasattr(w, "invoke")}
        buttons["Open"].invoke()
        self.assertEqual(opened, [path])
        with patch("tkinter.messagebox.askyesno", return_value=True):
            buttons["Delete"].invoke()
        self.assertEqual(view.user_rows, {})
        self.assertFalse(os.path.exists(path))


if __name__ == "__main__":
    unittest.main()
