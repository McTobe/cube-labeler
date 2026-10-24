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
import time
import unittest
from unittest.mock import patch

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# The GUI needs tkinter, which many Linux Pythons leave out
if importlib.util.find_spec("tkinter") is None:
    raise unittest.SkipTest("tkinter is not installed")

import customtkinter as ctk
from PIL import Image, ImageDraw

from core import icon_manager as im
from core.icon_manager import FAVOURITES, RECENT, USER_CATEGORY, IconManager
import ui.icon_browser as browser
import ui.icon_editor_dialog as editor


class FakeConfig:
    def __init__(self, user_dir):
        self.data = {}
        self.user_icons_dir = user_dir
        self.gemini_api_key = ""

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
        for target in (browser, editor):
            patcher = patch.object(target, "icon_manager", self.mgr)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.object(editor, "config_manager", config)
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

    def _picture(self, name="M3_hex-nut.png"):
        src = os.path.join(tempfile.mkdtemp(), name)
        self.addCleanup(shutil.rmtree, os.path.dirname(src), True)
        img = Image.new("RGB", (200, 160), "white")
        ImageDraw.Draw(img).ellipse((40, 30, 160, 130), outline="black", width=12)
        img.save(src)
        return src

    def _editor(self, dlg, **kwargs):
        with patch.object(dlg, "_take_grab"):
            ed = dlg._open_editor(**kwargs)
        self.addCleanup(lambda: ed.winfo_exists() and ed.destroy())
        ed.update()
        return ed

    def test_import_image_opens_editor_and_saves(self):
        src = self._picture()
        dlg = self._open(initial_category="Tools")
        with patch.object(browser.filedialog, "askopenfilename", return_value=src):
            dlg._import_image()
        ed = next(w for w in dlg.winfo_children() if isinstance(w, editor.IconEditorDialog))
        self.addCleanup(lambda: ed.winfo_exists() and ed.destroy())
        self.assertEqual(ed.entry_name.get(), "M3 hex nut")
        self.assertEqual(ed.cat_menu.get(), "Tools")
        self.assertEqual(str(ed.btn_save.cget("state")), "normal")
        ed._save(insert=False)
        self.assertTrue(dlg.selected_icon.user)
        self.assertEqual((dlg.selected_icon.title, dlg.selected_icon.category), ("M3 hex nut", "Tools"))
        self.assertEqual(self.chosen, [])

    def test_save_and_insert(self):
        dlg = self._open()
        ed = self._editor(dlg, picture_path=self._picture())
        ed._save(insert=True)
        self.assertEqual(len(self.chosen), 1)
        self.assertTrue(self.mgr.get_icon_by_path(self.chosen[0]).user)

    def test_edit_keeps_settings_and_touch_ups(self):
        dlg = self._open()
        ed = self._editor(dlg, picture_path=self._picture())
        ed._on_mode("Silhouette")
        ed._on_thickness("Bold")
        ed._render_now()
        ed.seg_tool.set("Pencil")

        class Click:
            x = y = 2
        ed._on_touch(Click(), start=True)
        ed._save(insert=False)
        icon = dlg.selected_icon

        ed2 = self._editor(dlg, icon=icon)
        self.assertEqual((ed2.edit.mode, ed2.edit.thickness), ("silhouette", 1))
        self.assertEqual(ed2.touch.getpixel((0, 0)), 1)
        self.assertEqual(ed2.title(), "Edit icon")
        ed2.entry_name.delete(0, "end")
        ed2.entry_name.insert(0, "Ring")
        ed2._on_thickness("Normal")
        ed2._save(insert=False)
        again = self.mgr.get_icon_by_path(icon.file_path)
        self.assertEqual(again.title, "Ring")
        self.assertEqual(self.mgr.edit_source(again)[1].thickness, 0)

    def test_edit_a_copy_of_a_built_in_icon(self):
        dlg = self._open()
        dlg._select_path(self.mgr.get_icon_by_id("torx").file_path)
        self.assertEqual(dlg.btn_edit.cget("text"), "Edit a copy…")
        ed = self._editor(dlg, icon=dlg.selected_icon)
        self.assertIsNone(ed.editing)
        self.assertEqual(ed.entry_name.get(), "Torx Star Drive (my copy)")
        ed._save(insert=False)
        self.assertTrue(dlg.selected_icon.user)
        self.assertTrue(os.path.isfile(self.mgr.get_icon_by_id("torx").file_path))

    def test_editor_starts_empty(self):
        dlg = self._open()
        ed = self._editor(dlg)
        self.assertIsNone(ed.source)
        self.assertEqual(str(ed.btn_save.cget("state")), "disabled")
        self.assertEqual(str(ed.btn_ai.cget("state")), "disabled")

    def test_custom_preset_shows_its_text_box(self):
        ed = self._editor(self._open())
        self.assertEqual(ed.entry_custom.winfo_manager(), "")
        ed.preset_menu.set(editor.CUSTOM)
        ed._on_preset(editor.CUSTOM)
        ed.update()
        self.assertEqual(ed.entry_custom.winfo_manager(), "pack")
        ed.preset_menu.set("Bold line drawing")
        ed._on_preset("Bold line drawing")
        ed.update()
        self.assertEqual(ed.entry_custom.winfo_manager(), "")

    def test_redraw_with_the_chosen_service(self):
        calls = []

        class FakeProvider:
            id, name, api_key = "openai", "OpenAI", "sk-test"

            def redraw(self, picture, preset, custom):
                calls.append((picture.size, preset, custom))
                return Image.new("RGB", (64, 64), "black")

        with patch.object(editor, "current_provider", FakeProvider):
            ed = self._editor(self._open(), picture_path=self._picture())
            self.assertEqual(ed.lbl_ai_title.cget("text"), "Redraw it with OpenAI")
            ed.preset_menu.set(editor.CUSTOM)
            ed._on_preset(editor.CUSTOM)
            with patch.object(editor.messagebox, "showinfo") as told:
                ed._redraw_with_ai()
            told.assert_called_once()
            ed.entry_custom.insert(0, "keep it round")
            ed._redraw_with_ai()
            for _ in range(50):
                ed.update()
                if not ed._busy:
                    break
                time.sleep(0.02)
        self.assertEqual(calls, [((200, 160), editor.CUSTOM, "keep it round")])
        self.assertIn("OpenAI's icon is ready", ed.lbl_status.cget("text"))
        self.assertIsNotNone(ed._picture_before_ai)

    def test_icons_page_has_nothing_to_insert(self):
        with patch("ui.backup_dialog.backup_status", lambda: ("Auto-backup off", "gray", False)):
            page = browser.IconLibraryPage(self.root)
        self.addCleanup(page.destroy)
        page.pack(fill="both", expand=True)
        page.update()
        page._select_path(self.mgr.get_icon_by_id("torx").file_path)
        page._confirm_selection()
        self.assertEqual(self.chosen, [])
        self.assertTrue(page.winfo_exists())
        self.assertEqual(page.lbl_backup.cget("text"), "Auto-backup off")
        self.assertEqual(page.btn_backups.cget("text"), "Backups…")
        with patch.object(page, "_take_grab"):
            ed = page._open_editor(picture_path=self._picture())
        self.addCleanup(lambda: ed.winfo_exists() and ed.destroy())
        ed.update()
        self.assertEqual(ed.btn_save_insert.winfo_manager(), "")
        ed._save(insert=False)
        page.refresh()
        self.assertEqual(page.selected_icon.title, "M3 hex nut")

    def test_picker_shows_backup_status(self):
        dlg = self._open()
        with patch("ui.backup_dialog.backup_status", lambda: ("● Auto-backup on: OneDrive", "green", True)):
            dlg._refresh_backup_status()
        self.assertEqual(dlg.lbl_backup.cget("text"), "● Auto-backup on: OneDrive")
        self.assertEqual(dlg.btn_backups.cget("text"), "Backups ✓")
        self.assertEqual(dlg.btn_use.cget("text"), "Insert icon")


if __name__ == "__main__":
    unittest.main()
