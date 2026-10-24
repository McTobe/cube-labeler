#!/usr/bin/env python3
"""
Headless GUI test for the icon backups window: export, import with a name clash and
turning automatic backups on and off.
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

from core import icon_backup as ib
from core import icon_manager as im
from core.icon_manager import IconManager
import ui.backup_dialog as bd


class FakeConfig:
    def __init__(self):
        self.data = {}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value


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
        self._patch(im, "config_manager", self.config)
        self.mgr = IconManager(user_dir=os.path.join(self.tmp, "icons"))
        self.auto = ib.AutoBackup(self.mgr, self.config, delay=60)
        self._patch(bd, "icon_manager", self.mgr)
        self._patch(bd, "auto_backup", self.auto)
        self._patch(ib, "cloud_folders", lambda: [("Google Drive", os.path.join(self.tmp, "My Drive"))])
        os.makedirs(os.path.join(self.tmp, "My Drive"))
        self.info = []
        self._patch(bd.messagebox, "showinfo", lambda title, text, **kw: self.info.append(text))
        self._patch(bd.messagebox, "showerror", lambda title, text, **kw: self.info.append("ERROR " + text))
        self._patch(bd.messagebox, "askyesno", lambda *a, **kw: True)
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

    def test_export_then_import_with_clash(self):
        self.mgr.save_user_icon(Image.new("RGBA", (32, 32), (0, 0, 0, 255)), "Nut")
        path = os.path.join(self.tmp, "b.cubeicons")
        dlg = self._open()
        with patch.object(bd.filedialog, "asksaveasfilename", return_value=path):
            dlg._export()
        self.assertTrue(os.path.isfile(path))
        self.assertIn("Saved 1 icons", self.info[-1])

        # Same name, different picture: the clash window asks, here "Keep both"
        self.mgr.replace_user_icon(self.mgr.user_icons()[0], Image.new("RGBA", (32, 32), (255, 255, 255, 255)),
                                   "Nut", "My Icons", [])

        def pick_keep_both(window):
            window.update()
            window._pick(ib.KEEP_BOTH)

        with patch.object(bd.filedialog, "askopenfilename", return_value=path), \
                patch.object(dlg, "wait_window", pick_keep_both):
            dlg._import()
        self.assertEqual(len(self.mgr.user_icons()), 2)
        self.assertEqual(self.changed, [1])
        self.assertIn("Added 1", self.info[-1])

    def test_says_when_no_cloud_folder_is_found(self):
        with patch.object(ib, "cloud_folders", lambda: []):
            dlg = self._open()
        self.assertIn("No Google Drive", dlg.lbl_clouds.cget("text"))
        self.assertEqual(dlg.cloud_row.winfo_children(), [])

    def test_import_rejects_other_files(self):
        path = os.path.join(self.tmp, "notes.cubeicons")
        with open(path, "w") as f:
            f.write("hello")
        dlg = self._open()
        with patch.object(bd.filedialog, "askopenfilename", return_value=path):
            dlg._import()
        self.assertTrue(self.info[-1].startswith("ERROR"))

    def test_turn_automatic_backup_on_and_off(self):
        self.mgr.save_user_icon(Image.new("RGBA", (32, 32), (0, 0, 0, 255)), "Nut")
        dlg = self._open()
        self.assertIn("Off", dlg.lbl_folder.cget("text"))
        self.assertEqual(dlg.btn_now.cget("state"), "disabled")
        self.assertIn("Found on this PC: Google Drive", dlg.lbl_clouds.cget("text"))
        cloud_button = dlg.cloud_row.winfo_children()[0]
        self.assertEqual(cloud_button.cget("text"), "Use Google Drive")
        cloud_button.invoke()
        folder = os.path.join(self.tmp, "My Drive", bd.BACKUP_SUBFOLDER)
        self.assertEqual(self.auto.folder, os.path.normpath(folder))
        self.assertEqual(len(self.auto.backups()), 1)
        self.assertIn("Last backup", dlg.lbl_status.cget("text"))
        dlg.btn_off.invoke()
        self.assertEqual(self.auto.folder, "")
        self.assertEqual(dlg.btn_now.cget("state"), "disabled")


if __name__ == "__main__":
    unittest.main()
