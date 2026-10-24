#!/usr/bin/env python3
"""
Tests for backups of the user's icons: export, import with name clashes, safety checks
and automatic backups to a folder.
"""

import io
import json
import os
import shutil
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from PIL import Image

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from core import icon_backup as ib
from core import icon_manager as im
from core.icon_editor import IconEdit
from core.icon_manager import IconManager


class FakeConfig:
    def __init__(self):
        self.data = {}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value


def square(colour=(0, 0, 0, 255), size=64):
    return Image.new("RGBA", (size, size), colour)


class BackupTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.config = FakeConfig()
        patcher = patch.object(im, "config_manager", self.config)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.mgr = IconManager(user_dir=os.path.join(self.tmp, "icons"))

    def other_manager(self, name="other"):
        return IconManager(user_dir=os.path.join(self.tmp, name))

    def backup_bytes(self, mgr=None):
        buf = io.BytesIO()
        ib.write_backup(mgr or self.mgr, buf)
        buf.seek(0)
        return buf


class TestExportImport(BackupTestCase):
    def test_round_trip_keeps_everything(self):
        edit = IconEdit(invert=True, thickness=2)
        touch = Image.new("L", (64, 64), 0)
        touch.putpixel((3, 3), 255)
        icon = self.mgr.save_user_icon(square(), "Nut M3", category="Fasteners", keywords=["nut", "m3"],
                                       original=square((200, 0, 0, 255), 100), edit=edit, touch=touch)
        self.mgr.save_user_icon(square(), "Plain")
        self.mgr.toggle_favourite(icon)
        data = self.backup_bytes()

        backup = ib.read_backup(data)
        self.assertEqual(len(backup.icons), 2)

        other = self.other_manager()
        result = ib.restore_backup(other, backup)
        self.assertEqual(result.added, 2)
        restored = other.get_icon_by_id("Nut_M3")
        self.assertEqual(restored.title, "Nut M3")
        self.assertEqual(restored.category, "Fasteners")
        self.assertEqual(restored.keywords, ["nut", "m3"])
        self.assertTrue(other.is_favourite(restored))
        original, restored_edit, restored_touch = other.edit_source(restored)
        self.assertEqual(original.size, (100, 100))
        self.assertTrue(restored_edit.invert)
        self.assertEqual(restored_edit.thickness, 2)
        self.assertEqual(restored_touch.getpixel((3, 3)), 255)
        self.assertFalse(other.is_favourite(other.get_icon_by_id("Plain")))

    def test_same_icons_are_left_alone(self):
        self.mgr.save_user_icon(square(), "Nut")
        result = ib.restore_backup(self.mgr, ib.read_backup(self.backup_bytes()))
        self.assertEqual((result.added, result.unchanged), (0, 1))
        self.assertEqual(len(self.mgr.user_icons()), 1)

    def test_name_clashes(self):
        self.mgr.save_user_icon(square(), "Nut")
        other = self.other_manager()
        other.save_user_icon(square((255, 255, 255, 255)), "Nut")
        backup = ib.read_backup(self.backup_bytes())
        plan = ib.plan_import(other, backup)
        self.assertEqual(len(plan.conflicts), 1)

        self.assertEqual(ib.restore_backup(other, backup, ib.SKIP).skipped, 1)
        self.assertEqual(len(other.user_icons()), 1)

        self.assertEqual(ib.restore_backup(other, backup, ib.KEEP_BOTH).added, 1)
        self.assertEqual(sorted(i.id for i in other.user_icons()), ["Nut", "Nut_1"])

        result = ib.restore_backup(other, backup, ib.REPLACE)
        self.assertEqual(result.replaced, 1)
        with Image.open(other.get_icon_by_id("Nut").file_path) as img:
            self.assertEqual(img.convert("RGBA").getpixel((0, 0)), (0, 0, 0, 255))

    def test_import_tells_listeners_once(self):
        self.mgr.save_user_icon(square(), "A")
        self.mgr.save_user_icon(square(), "B")
        other = self.other_manager()
        calls = []
        other.change_listeners.append(lambda: calls.append(1))
        ib.restore_backup(other, ib.read_backup(self.backup_bytes()))
        self.assertEqual(len(calls), 1)

    def test_export_file(self):
        self.mgr.save_user_icon(square(), "A")
        path = os.path.join(self.tmp, "mine" + ib.BACKUP_EXTENSION)
        self.assertEqual(ib.export_backup(self.mgr, path), 1)
        self.assertFalse(os.path.exists(path + ".part"))
        self.assertEqual(ib.import_backup(self.other_manager(), path).added, 1)


class TestBadBackups(BackupTestCase):
    def zip_with(self, manifest, files=None):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr(ib.MANIFEST, json.dumps(manifest))
            for name, data in (files or {}).items():
                zf.writestr(name, data)
        buf.seek(0)
        return buf

    def png(self):
        buf = io.BytesIO()
        square().save(buf, "PNG")
        return buf.getvalue()

    def test_not_a_zip(self):
        with self.assertRaises(ib.BackupError):
            ib.read_backup(io.BytesIO(b"hello"))

    def test_wrong_format_or_newer_version(self):
        with self.assertRaises(ib.BackupError):
            ib.read_backup(self.zip_with({"format": "something", "version": 1, "icons": []}))
        with self.assertRaisesRegex(ib.BackupError, "newer"):
            ib.read_backup(self.zip_with({"format": ib.FORMAT_NAME, "version": 99, "icons": []}))

    def test_paths_outside_the_folder_are_ignored(self):
        manifest = {"format": ib.FORMAT_NAME, "version": 1,
                    "icons": [{"file": "../evil.png"}, {"file": "..\\evil.png"}, {"file": "ok.png"}]}
        backup = ib.read_backup(self.zip_with(manifest, {"icons/ok.png": self.png(),
                                                          "icons/../evil.png": self.png()}))
        self.assertEqual([i.file for i in backup.icons], ["ok.png"])

    def test_broken_picture(self):
        manifest = {"format": ib.FORMAT_NAME, "version": 1, "icons": [{"file": "a.png"}]}
        with self.assertRaises(ib.BackupError):
            ib.read_backup(self.zip_with(manifest, {"icons/a.png": b"not a png"}))

    def test_edit_settings_without_original_are_dropped(self):
        manifest = {"format": ib.FORMAT_NAME, "version": 1,
                    "icons": [{"file": "a.png", "meta": {"title": "A", "edit": {"invert": True}}}]}
        backup = ib.read_backup(self.zip_with(manifest, {"icons/a.png": self.png()}))
        self.assertNotIn("edit", backup.icons[0].meta)


class TestAutoBackup(BackupTestCase):
    def setUp(self):
        super().setUp()
        self.folder = os.path.join(self.tmp, "Google Drive")
        os.makedirs(self.folder)
        self.auto = ib.AutoBackup(self.mgr, self.config, delay=60)

    def test_off_without_a_folder(self):
        self.mgr.save_user_icon(square(), "A")
        self.assertIsNone(self.auto.backup_now())
        self.assertIsNone(self.auto._timer)

    def test_writes_and_skips_when_unchanged(self):
        self.auto.folder = self.folder
        self.assertIsNone(self.auto.backup_now(), "no icons, no backup")
        self.mgr.save_user_icon(square(), "A")
        path = self.auto.backup_now()
        self.assertTrue(os.path.basename(path).startswith(ib.AUTO_PREFIX))
        self.assertEqual(len(ib.read_backup(open(path, "rb")).icons), 1)
        self.assertIsNone(self.auto.backup_now())
        self.assertTrue(self.auto.last_backup)
        self.assertEqual(self.auto.backups(), [path])

    def test_change_schedules_one_backup(self):
        self.auto.folder = self.folder
        self.mgr.save_user_icon(square(), "A")
        self.mgr.save_user_icon(square(), "B")
        self.assertEqual(self.auto.backups(), [])
        self.auto.flush()
        backups = self.auto.backups()
        self.assertEqual(len(backups), 1)
        self.assertEqual(len(ib.read_backup(open(backups[0], "rb")).icons), 2)

    def test_keeps_only_the_newest(self):
        self.auto.folder = self.folder
        self.config.set("icon_backup_keep", 3)
        other_file = os.path.join(self.folder, "my notes.txt")
        open(other_file, "w").close()
        for n in range(5):
            self.mgr.save_user_icon(square(), f"Icon {n}")
            self.auto.backup_now()
        self.assertEqual(len(self.auto.backups()), 3)
        self.assertTrue(os.path.exists(other_file))
        newest = ib.read_backup(open(self.auto.backups()[0], "rb"))
        self.assertEqual(len(newest.icons), 5)

    def test_missing_folder_is_reported(self):
        self.auto.folder = os.path.join(self.tmp, "gone")
        self.mgr.save_user_icon(square(), "A")
        with self.assertRaises(OSError):
            self.auto.backup_now()
        self.assertIn("not there", self.auto.last_error)


if __name__ == "__main__":
    unittest.main()
