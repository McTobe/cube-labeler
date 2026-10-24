#!/usr/bin/env python3
"""
Headless GUI test for the backups window: export, restoring chosen parts with a name
clash, the automatic backup switch and the status shown in the library and Settings.
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

if importlib.util.find_spec("tkinter") is None:
    raise unittest.SkipTest("tkinter is not installed")

import customtkinter as ctk
from PIL import Image

from core import backup as bk
from core import icon_manager as im
from core.config import is_local_setting
from core.icon_manager import IconManager
import ui.backup_dialog as bd


class FakeConfig:
    def __init__(self):
        self.data = {}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value

    def backup_settings(self):
        return {k: v for k, v in self.data.items() if not is_local_setting(k)}

    def restore_settings(self, data):
        self.data.update({k: v for k, v in data.items() if not is_local_setting(k)})


def black(size=32):
    return Image.new("RGBA", (size, size), (0, 0, 0, 255))


class TestBackupDialog(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.root = ctk.CTk()
        except Exception as e:
            raise unittest.SkipTest(f"no display: {e}")
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.config = FakeConfig()
        self.data_dir = os.path.join(self.tmp, "app")
        self._patch(im, "config_manager", self.config)
        self._patch(bk, "config_manager", self.config)
        self._patch(bk, "CONFIG_DIR", self.data_dir)
        self.mgr = IconManager(user_dir=os.path.join(self.data_dir, "icons"))
        self.auto = bk.AutoBackup(self.mgr, self.config, delay=60)
        self.addCleanup(lambda: self.auto._timer and self.auto._timer.cancel())
        self._patch(bd, "icon_manager", self.mgr)
        self._patch(bd, "auto_backup", self.auto)
        self.drive = os.path.join(self.tmp, "My Drive")
        os.makedirs(self.drive)
        self._patch(bk, "cloud_folders", lambda: [("Google Drive", self.drive)])
        self.info = []
        self._patch(bd.messagebox, "showinfo", lambda title, text, **kw: self.info.append(text))
        self._patch(bd.messagebox, "showerror", lambda title, text, **kw: self.info.append("ERROR " + text))
        self.changed = []

    def _patch(self, target, name, value):
        patcher = patch.object(target, name, value)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _open(self):
        dlg = bd.BackupDialog(self.root, on_changed=lambda: self.changed.append(1))
        self.addCleanup(lambda: dlg.winfo_exists() and dlg.destroy())
        dlg.update()
        return dlg

    def _restore_with(self, dlg, path, answer):
        """Restores `path`, answering the restore window with answer(window)."""
        def answer_window(window):
            window.update()
            answer(window)

        with patch.object(bd.filedialog, "askopenfilename", return_value=path), \
                patch.object(dlg, "wait_window", answer_window):
            dlg._import()

    def test_export_then_restore_chosen_parts_with_clash(self):
        self.mgr.save_user_icon(black(), "Nut")
        self.config.data["label_language"] = "sv"
        path = os.path.join(self.tmp, "b.cubebackup")
        dlg = self._open()
        with patch.object(bd.filedialog, "asksaveasfilename", return_value=path):
            dlg._export()
        self.assertTrue(os.path.isfile(path))
        self.assertIn("Saved 1 icons, 0 templates and your settings", self.info[-1])

        # Same name, different picture; settings changed since
        self.mgr.replace_user_icon(self.mgr.user_icons()[0], Image.new("RGBA", (32, 32), (255, 255, 255, 255)),
                                   "Nut", "My Icons", [])
        self.config.data["label_language"] = "en"

        def keep_both_icons_only(window):
            self.assertEqual(sorted(window.part_vars), [bk.ICONS, bk.SETTINGS])
            self.assertTrue(window.clash_box.winfo_manager())
            window.part_vars[bk.SETTINGS].set(False)
            window.clash_var.set("Keep both")
            window._restore()

        self._restore_with(dlg, path, keep_both_icons_only)
        self.assertEqual(len(self.mgr.user_icons()), 2)
        self.assertEqual(self.config.data["label_language"], "en")
        self.assertEqual(self.changed, [1])
        self.assertIn("Icons: added 1", self.info[-1])

        def settings_only(window):
            window.part_vars[bk.ICONS].set(False)
            window._restore()

        self._restore_with(dlg, path, settings_only)
        self.assertEqual(self.config.data["label_language"], "sv")
        self.assertIn("Settings restored", self.info[-1])

    def test_cancel_restores_nothing(self):
        self.mgr.save_user_icon(black(), "Nut")
        path = os.path.join(self.tmp, "b.cubebackup")
        bk.export_backup(self.mgr, path)
        other = IconManager(user_dir=os.path.join(self.tmp, "other"))
        self._patch(bd, "icon_manager", other)
        dlg = self._open()
        self._restore_with(dlg, path, lambda window: window.destroy())
        self.assertEqual(other.user_icons(), [])

    def test_restore_rejects_other_files(self):
        path = os.path.join(self.tmp, "notes.cubebackup")
        with open(path, "w") as f:
            f.write("hello")
        dlg = self._open()
        with patch.object(bd.filedialog, "askopenfilename", return_value=path):
            dlg._import()
        self.assertTrue(self.info[-1].startswith("ERROR"))

    def test_turn_automatic_backup_on_and_off(self):
        self.mgr.save_user_icon(black(), "Nut")
        self.assertEqual(bd.backup_status()[0], "Auto-backup off")
        dlg = self._open()
        self.assertIn("Off", dlg.lbl_folder.cget("text"))
        self.assertEqual(dlg.btn_now.cget("state"), "disabled")
        self.assertIn("Found on this PC: Google Drive", dlg.lbl_clouds.cget("text"))
        cloud_button = dlg.cloud_row.winfo_children()[0]
        self.assertEqual(cloud_button.cget("text"), "Use Google Drive")
        cloud_button.invoke()
        folder = os.path.join(self.drive, bd.BACKUP_SUBFOLDER)
        self.assertEqual(self.auto.folder, os.path.normpath(folder))
        self.assertEqual(len(self.auto.backups()), 1)
        self.assertIn("Last backup", dlg.lbl_status.cget("text"))
        text, _colour, on = bd.backup_status()
        self.assertTrue(on)
        self.assertTrue(text.startswith("● Auto-backup on: Google Drive · last "))
        dlg.btn_off.invoke()
        self.assertEqual(self.auto.folder, "")
        self.assertEqual(dlg.btn_now.cget("state"), "disabled")

    def test_status_names_a_plain_folder_and_failures(self):
        self.auto.folder = os.path.join(self.tmp, "Backups here")
        self.assertEqual(bd.backup_status()[0], "● Auto-backup on: Backups here")
        self.config.data["icon_backup_error"] = "disk full"
        self.assertEqual(bd.backup_status()[0], "● Auto-backup to Backups here failed")

    def test_says_when_no_cloud_folder_is_found(self):
        with patch.object(bk, "cloud_folders", lambda: []):
            dlg = self._open()
        self.assertIn("No Google Drive", dlg.lbl_clouds.cget("text"))
        self.assertEqual(dlg.cloud_row.winfo_children(), [])


if __name__ == "__main__":
    unittest.main()
