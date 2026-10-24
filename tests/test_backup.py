#!/usr/bin/env python3
"""
Tests for backups: icons, settings and templates in one file, restoring chosen parts,
name clashes, old icon-only backups, safety checks and automatic backups to a folder.
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

from core import backup as bk
from core import icon_manager as im
from core.config import is_local_setting
from core.icon_editor import IconEdit
from core.icon_manager import IconManager


class FakeConfig:
    """Settings in memory, with the same backup rules as the real config."""

    def __init__(self):
        self.data = {}
        self.change_listeners = []

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
        for listener in self.change_listeners:
            listener()

    def backup_settings(self):
        return {k: v for k, v in self.data.items() if not is_local_setting(k)}

    def restore_settings(self, data):
        for k, v in data.items():
            if not is_local_setting(k):
                self.data[k] = v


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
        self.data_dir = os.path.join(self.tmp, "app")
        self.mgr = IconManager(user_dir=os.path.join(self.data_dir, "icons"))

    def other_pc(self, name="other"):
        """A second PC: its own data folder and settings."""
        data_dir = os.path.join(self.tmp, name)
        return IconManager(user_dir=os.path.join(data_dir, "icons")), data_dir

    def write_template(self, name, data, data_dir=None):
        folder = os.path.join(data_dir or self.data_dir, "templates")
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, name), "w", encoding="utf-8") as f:
            json.dump(data, f)

    def backup_file(self):
        buf = io.BytesIO()
        bk.write_backup(bk.collect(self.mgr, self.config, self.data_dir), buf)
        buf.seek(0)
        return buf


class TestWhatGoesIn(BackupTestCase):
    def test_settings_without_this_pcs_own_or_keys(self):
        self.config.data.update({
            "label_language": "sv", "ai_provider": "openai", "some_future_setting": 3,
            "gemini_api_key_protected": "SECRET", "openai_api_key": "sk-x",
            "last_serial_port": "COM5", "icon_backup_folder": "G:/x",
        })
        backup = bk.read_backup(self.backup_file())
        self.assertEqual(backup.settings, {"label_language": "sv", "ai_provider": "openai", "some_future_setting": 3})

    def test_other_data_files_but_not_icons_config_or_backups(self):
        self.write_template("Shelf.json", {"text": "Shelf"})
        os.makedirs(os.path.join(self.data_dir, "fonts"))
        with open(os.path.join(self.data_dir, "fonts", "mine.ttf"), "wb") as f:
            f.write(b"font")
        for name in ("config.json", "config.json.tmp"):
            with open(os.path.join(self.data_dir, name), "w") as f:
                f.write("{}")
        backups = os.path.join(self.data_dir, "backups")
        os.makedirs(backups)
        open(os.path.join(backups, "old.cubebackup"), "w").close()
        self.config.data["icon_backup_folder"] = backups
        self.mgr.save_user_icon(square(), "Nut")

        backup = bk.read_backup(self.backup_file())
        self.assertEqual(sorted(backup.files), ["fonts/mine.ttf", "templates/Shelf.json"])
        self.assertEqual(list(backup.templates), ["templates/Shelf.json"])
        self.assertEqual(backup.parts, [bk.ICONS, bk.SETTINGS, bk.TEMPLATES])


class TestRestore(BackupTestCase):
    def test_round_trip_keeps_everything(self):
        edit = IconEdit(invert=True, thickness=2)
        touch = Image.new("L", (64, 64), 0)
        touch.putpixel((3, 3), 255)
        icon = self.mgr.save_user_icon(square(), "Nut M3", category="Fasteners", keywords=["nut", "m3"],
                                       original=square((200, 0, 0, 255), 100), edit=edit, touch=touch)
        self.mgr.save_user_icon(square(), "Plain")
        self.mgr.toggle_favourite(icon)
        self.config.data["label_language"] = "sv"
        self.write_template("Shelf.json", {"text": "Shelf"})
        data = self.backup_file()

        # A fresh PC: no icons, favourites or settings yet
        self.config.data.clear()
        other, other_dir = self.other_pc()
        result = bk.restore_backup(other, bk.read_backup(data), config=self.config, data_dir=other_dir)
        self.assertEqual((result.added, result.templates_added, result.settings_restored), (2, 1, True))
        restored = other.get_icon_by_id("Nut_M3")
        self.assertEqual((restored.title, restored.category, restored.keywords), ("Nut M3", "Fasteners", ["nut", "m3"]))
        self.assertTrue(other.is_favourite(restored))
        original, restored_edit, restored_touch = other.edit_source(restored)
        self.assertEqual(original.size, (100, 100))
        self.assertTrue(restored_edit.invert)
        self.assertEqual(restored_touch.getpixel((3, 3)), 255)
        self.assertEqual(self.config.data["label_language"], "sv")
        with open(os.path.join(other_dir, "templates", "Shelf.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"text": "Shelf"})

    def test_restore_only_chosen_parts(self):
        self.mgr.save_user_icon(square(), "Nut")
        self.config.data["label_language"] = "sv"
        self.write_template("Shelf.json", {"text": "Shelf"})
        backup = bk.read_backup(self.backup_file())
        self.config.data["label_language"] = "en"
        other, other_dir = self.other_pc()
        result = bk.restore_backup(other, backup, parts=[bk.TEMPLATES], config=self.config, data_dir=other_dir)
        self.assertEqual((result.added, result.templates_added, result.settings_restored), (0, 1, False))
        self.assertEqual(other.user_icons(), [])
        self.assertEqual(self.config.data["label_language"], "en")

    def test_restore_keeps_this_pcs_keys(self):
        self.config.data["gemini_api_key_protected"] = "MINE"
        backup = bk.read_backup(self.backup_file())
        backup.settings["gemini_api_key_protected"] = "FROM A HOSTILE FILE"
        bk.restore_backup(self.mgr, backup, config=self.config, data_dir=self.data_dir)
        self.assertEqual(self.config.data["gemini_api_key_protected"], "MINE")

    def test_same_icons_are_left_alone(self):
        self.mgr.save_user_icon(square(), "Nut")
        result = bk.restore_backup(self.mgr, bk.read_backup(self.backup_file()), parts=[bk.ICONS],
                                   config=self.config, data_dir=self.data_dir)
        self.assertEqual((result.added, result.unchanged), (0, 1))
        self.assertEqual(len(self.mgr.user_icons()), 1)

    def test_name_clashes_for_icons_and_templates(self):
        self.mgr.save_user_icon(square(), "Nut")
        self.write_template("Shelf.json", {"text": "Shelf"})
        backup = bk.read_backup(self.backup_file())
        other, other_dir = self.other_pc()
        other.save_user_icon(square((255, 255, 255, 255)), "Nut")
        self.write_template("Shelf.json", {"text": "Other shelf"}, other_dir)
        plan = bk.plan_import(other, backup, other_dir)
        self.assertEqual((len(plan.conflicts), plan.template_conflicts), (1, ["templates/Shelf.json"]))

        kwargs = dict(parts=[bk.ICONS, bk.TEMPLATES], config=self.config, data_dir=other_dir)
        result = bk.restore_backup(other, backup, bk.SKIP, **kwargs)
        self.assertEqual((result.skipped, result.templates_skipped), (1, 1))

        result = bk.restore_backup(other, backup, bk.KEEP_BOTH, **kwargs)
        self.assertEqual((result.added, result.templates_added), (1, 1))
        self.assertEqual(sorted(i.id for i in other.user_icons()), ["Nut", "Nut_1"])
        self.assertTrue(os.path.isfile(os.path.join(other_dir, "templates", "Shelf (2).json")))

        result = bk.restore_backup(other, backup, bk.REPLACE, **kwargs)
        self.assertEqual((result.replaced, result.templates_replaced), (1, 1))
        with open(os.path.join(other_dir, "templates", "Shelf.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"text": "Shelf"})

    def test_restore_tells_listeners_once(self):
        self.mgr.save_user_icon(square(), "A")
        self.mgr.save_user_icon(square(), "B")
        other, other_dir = self.other_pc()
        calls = []
        other.change_listeners.append(lambda: calls.append(1))
        bk.restore_backup(other, bk.read_backup(self.backup_file()), config=self.config, data_dir=other_dir)
        self.assertEqual(len(calls), 1)

    def test_export_file(self):
        self.mgr.save_user_icon(square(), "A")
        path = os.path.join(self.tmp, "mine" + bk.BACKUP_EXTENSION)
        backup = bk.export_backup(self.mgr, path, self.config, self.data_dir)
        self.assertEqual(len(backup.icons), 1)
        self.assertFalse(os.path.exists(path + ".part"))
        other, other_dir = self.other_pc()
        self.assertEqual(bk.import_backup(other, path, config=self.config, data_dir=other_dir).added, 1)


class TestBadAndOldBackups(BackupTestCase):
    def zip_with(self, manifest, files=None):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr(bk.MANIFEST, json.dumps(manifest))
            for name, data in (files or {}).items():
                zf.writestr(name, data)
        buf.seek(0)
        return buf

    def png(self):
        buf = io.BytesIO()
        square().save(buf, "PNG")
        return buf.getvalue()

    def test_old_icon_only_backup(self):
        manifest = {"format": bk.OLD_ICON_FORMAT, "version": 1,
                    "icons": [{"file": "a.png", "favourite": True, "meta": {"title": "A"}}]}
        backup = bk.read_backup(self.zip_with(manifest, {"icons/a.png": self.png()}))
        self.assertIsNone(backup.settings)
        self.assertEqual(backup.parts, [bk.ICONS])
        result = bk.restore_backup(self.mgr, backup, config=self.config, data_dir=self.data_dir)
        self.assertEqual((result.added, result.settings_restored), (1, False))
        self.assertTrue(self.mgr.is_favourite(self.mgr.get_icon_by_id("a")))

    def test_not_a_zip(self):
        with self.assertRaises(bk.BackupError):
            bk.read_backup(io.BytesIO(b"hello"))

    def test_wrong_format_or_newer_version(self):
        with self.assertRaises(bk.BackupError):
            bk.read_backup(self.zip_with({"format": "something", "version": 1, "icons": []}))
        with self.assertRaisesRegex(bk.BackupError, "newer"):
            bk.read_backup(self.zip_with({"format": bk.FORMAT_NAME, "version": 99, "icons": []}))

    def test_paths_outside_the_folder_are_ignored(self):
        manifest = {"format": bk.FORMAT_NAME, "version": 2,
                    "icons": [{"file": "../evil.png"}, {"file": "..\\evil.png"}, {"file": "ok.png"}],
                    "files": ["../evil.txt", "templates/../../evil.json", "C:/evil", "templates\\x.json",
                              "config.json", "icons/sneaky.png", ".hidden", "templates/ok.json"]}
        files = {"icons/ok.png": self.png(), "data/templates/ok.json": b"{}"}
        for path in manifest["files"][:-1]:
            files[f"data/{path}"] = b"x"
        backup = bk.read_backup(self.zip_with(manifest, files))
        self.assertEqual([i.file for i in backup.icons], ["ok.png"])
        self.assertEqual(list(backup.files), ["templates/ok.json"])

    def test_broken_picture(self):
        manifest = {"format": bk.FORMAT_NAME, "version": 2, "icons": [{"file": "a.png"}]}
        with self.assertRaises(bk.BackupError):
            bk.read_backup(self.zip_with(manifest, {"icons/a.png": b"not a png"}))

    def test_edit_settings_without_original_are_dropped(self):
        manifest = {"format": bk.FORMAT_NAME, "version": 2,
                    "icons": [{"file": "a.png", "meta": {"title": "A", "edit": {"invert": True}}}]}
        backup = bk.read_backup(self.zip_with(manifest, {"icons/a.png": self.png()}))
        self.assertNotIn("edit", backup.icons[0].meta)


class TestAutoBackup(BackupTestCase):
    def setUp(self):
        super().setUp()
        self.folder = os.path.join(self.tmp, "Google Drive")
        os.makedirs(self.folder)
        self.auto = bk.AutoBackup(self.mgr, self.config, self.data_dir, delay=60)
        self.addCleanup(lambda: self.auto._timer and self.auto._timer.cancel())

    def test_off_without_a_folder(self):
        self.mgr.save_user_icon(square(), "A")
        self.assertIsNone(self.auto.backup_now())
        self.assertIsNone(self.auto._timer)

    def test_writes_and_skips_when_unchanged(self):
        self.auto.folder = self.folder
        self.mgr.save_user_icon(square(), "A")
        path = self.auto.backup_now()
        self.assertTrue(os.path.basename(path).startswith(bk.AUTO_PREFIX))
        self.assertTrue(path.endswith(bk.BACKUP_EXTENSION))
        self.assertEqual(len(bk.read_backup(open(path, "rb")).icons), 1)
        self.assertIsNone(self.auto.backup_now())
        self.assertTrue(self.auto.last_backup)
        self.assertEqual(self.auto.backups(), [path])

    def test_settings_changes_make_a_backup_but_recent_icons_do_not(self):
        self.auto.folder = self.folder
        self.assertIsNotNone(self.auto.backup_now())
        self.config.set("icon_recent", ["user/a.png"])
        self.assertIsNone(self.auto.backup_now())
        self.config.set("label_language", "sv")
        self.assertIsNotNone(self.auto.backup_now())

    def test_a_change_schedules_one_backup(self):
        self.auto.folder = self.folder
        self.auto.flush()
        before = len(self.auto.backups())
        self.mgr.save_user_icon(square(), "A")
        self.config.set("label_language", "sv")
        self.mgr.save_user_icon(square(), "B")
        self.assertIsNotNone(self.auto._timer)
        self.auto.flush()
        self.assertEqual(len(self.auto.backups()), before + 1)
        self.assertEqual(len(bk.read_backup(open(self.auto.backups()[0], "rb")).icons), 2)

    def test_keeps_only_the_newest(self):
        self.auto.folder = self.folder
        self.config.set("icon_backup_keep", 3)
        other_file = os.path.join(self.folder, "my notes.txt")
        old_icons_backup = os.path.join(self.folder, "Cube Labeler icons 2026-10-01 120000.cubeicons")
        for path in (other_file, old_icons_backup):
            open(path, "w").close()
        for n in range(5):
            self.mgr.save_user_icon(square(), f"Icon {n}")
            self.auto.backup_now()
        self.assertEqual(len(self.auto.backups()), 3)
        self.assertTrue(os.path.exists(other_file))
        self.assertTrue(os.path.exists(old_icons_backup))
        self.assertEqual(len(bk.read_backup(open(self.auto.backups()[0], "rb")).icons), 5)

    def test_missing_folder_is_reported(self):
        self.auto.folder = os.path.join(self.tmp, "gone")
        with self.assertRaises(OSError):
            self.auto.backup_now()
        self.assertIn("not there", self.auto.last_error)


if __name__ == "__main__":
    unittest.main()
