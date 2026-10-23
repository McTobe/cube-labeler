#!/usr/bin/env python3
"""
Headless GUI test for the icon library window: sidebar, search, details, favourites,
the user's own icons and inserting an icon.
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

# The GUI needs tkinter, which many Linux Pythons leave out
if importlib.util.find_spec("tkinter") is None:
    raise unittest.SkipTest("tkinter is not installed")

import customtkinter as ctk
from PIL import Image

from core import icon_manager as im
from core.icon_manager import FAVOURITES, RECENT, USER_CATEGORY, IconManager
import ui.icon_browser as browser


class FakeConfig:
    def __init__(self, user_dir):
        self.data = {}
        self.user_icons_dir = user_dir

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value


class TestIconBrowser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.root = ctk.CTk()
        except Exception as e:  # no display
            raise unittest.SkipTest(f"no display: {e}")
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        self.user_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.user_dir, True)
        config = FakeConfig(self.user_dir)
        for target in (im, browser):
            patcher = patch.object(target, "config_manager", config)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.mgr = IconManager(user_dir=self.user_dir)
        patcher = patch.object(browser, "icon_manager", self.mgr)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.chosen = []

    def _open(self, **kwargs):
        dlg = browser.IconBrowserDialog(self.root, on_select=self.chosen.append, **kwargs)
        self.addCleanup(lambda: dlg.winfo_exists() and dlg.destroy())
        dlg.update()
        return dlg

    def _shown_ids(self, dlg):
        return [i.id for i in dlg._shown]

    def test_sidebar_lists_every_view_with_counts(self):
        dlg = self._open(initial_category="Screw drives")
        self.assertEqual(list(dlg._sidebar_buttons), self.mgr.views)
        self.assertIn("(6)", dlg._sidebar_buttons["Screw drives"].cget("text"))
        self.assertEqual(sorted(self._shown_ids(dlg)), sorted(i.id for i in self.mgr.list_icons("Screw drives")))

    def test_unknown_initial_category_shows_all(self):
        dlg = self._open(initial_category="Engineering")
        self.assertEqual(dlg.category_var.get(), "All")
        self.assertEqual(len(dlg._shown), len(self.mgr.list_icons()))

    def test_search_and_category(self):
        dlg = self._open()
        dlg._select_category("Wiring & connectors")
        dlg.entry_search.insert(0, "wago")
        dlg._refresh_icons()
        self.assertEqual(self._shown_ids(dlg), ["wago_221"])
        dlg._clear_search()
        self.assertGreater(len(dlg._shown), 1)

    def test_select_favourite_and_insert(self):
        dlg = self._open()
        dlg._select_path(self.mgr.get_icon_by_id("torx").file_path)
        self.assertEqual(dlg.lbl_name.cget("text"), "Torx Star Drive")
        self.assertIsNotNone(dlg._print_image)
        dlg._toggle_favourite()
        self.assertIn("★", dlg.btn_fav.cget("text"))
        dlg._select_category(FAVOURITES)
        self.assertEqual(self._shown_ids(dlg), ["torx"])
        dlg._confirm_selection()
        self.assertEqual(self.chosen, [self.mgr.get_icon_by_id("torx").file_path])
        self.assertEqual([i.id for i in self.mgr.list_icons(RECENT)], ["torx"])

    def test_edit_and_delete_own_icon(self):
        item = self.mgr.save_user_icon(Image.new("RGBA", (64, 64), (0, 0, 0, 255)), "mine")
        dlg = self._open(initial_category=USER_CATEGORY)
        dlg._select_path(item.file_path)
        self.assertEqual(dlg.user_box.winfo_manager(), "pack")
        dlg.entry_title.delete(0, "end")
        dlg.entry_title.insert(0, "Spice jar")
        dlg.cat_menu.set("Symbols")
        dlg.entry_keywords.delete(0, "end")
        dlg.entry_keywords.insert(0, "krydda, burk")
        dlg._save_user_details()
        updated = self.mgr.get_icon_by_path(item.file_path)
        self.assertEqual((updated.title, updated.category, updated.keywords), ("Spice jar", "Symbols", ["krydda", "burk"]))
        self.assertEqual(dlg.selected_icon.file_path, item.file_path)

        with patch.object(browser.messagebox, "askyesno", return_value=True):
            dlg._delete_user_icon()
        self.assertFalse(os.path.exists(item.file_path))
        self.assertIsNone(dlg.selected_icon)
        self.assertEqual(dlg.user_box.winfo_manager(), "")
        self.assertEqual(dlg._shown, [])

    def test_import_image(self):
        src = os.path.join(self.user_dir, "..", os.path.basename(self.user_dir) + "_src.png")
        Image.new("RGB", (100, 100), "white").save(src)  # a picture to pick in the file dialog
        self.addCleanup(os.remove, src)
        dlg = self._open(initial_category="Tools")
        with patch.object(browser.filedialog, "askopenfilename", return_value=src):
            with patch("core.ai_generator.post_process_thermal", return_value=Image.new("RGBA", (256, 256), (0, 0, 0, 255))):
                dlg._import_image()
        self.assertTrue(dlg.selected_icon.user)
        self.assertEqual(dlg.selected_icon.category, "Tools")


if __name__ == "__main__":
    unittest.main()
