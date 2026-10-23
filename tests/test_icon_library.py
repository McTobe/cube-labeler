#!/usr/bin/env python3
"""
Tests for the icon library backend: views, favourites, recently used and the user's own icons.
"""

import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from core import icon_manager as im
from core.icon_manager import FAVOURITES, RECENT, USER_CATEGORY, IconManager, parse_keywords, print_preview


class FakeConfig:
    """Keeps favourites and recent icons in memory instead of the user's config.json."""

    def __init__(self):
        self.data = {}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value


class TestIconLibrary(unittest.TestCase):
    def setUp(self):
        self.user_dir = tempfile.mkdtemp()
        self.config = FakeConfig()
        patcher = patch.object(im, "config_manager", self.config)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(shutil.rmtree, self.user_dir, True)
        self.mgr = IconManager(user_dir=self.user_dir)

    def _black_square(self):
        return Image.new("RGBA", (64, 64), (0, 0, 0, 255))

    def test_sidebar_views(self):
        views = self.mgr.views
        self.assertEqual(views[:3], ["All", FAVOURITES, RECENT])
        self.assertEqual(views[-1], USER_CATEGORY)
        self.assertNotIn(USER_CATEGORY, self.mgr.built_in_categories)
        counts = self.mgr.category_counts()
        self.assertEqual(counts["All"], len(self.mgr.list_icons()))
        self.assertEqual(counts[FAVOURITES], 0)

    def test_favourites(self):
        torx = self.mgr.get_icon_by_id("torx")
        self.assertTrue(self.mgr.toggle_favourite(torx))
        self.assertEqual([i.id for i in self.mgr.list_icons(FAVOURITES)], ["torx"])
        self.assertEqual(self.config.data["icon_favourites"], ["screw_drives/torx.png"])
        self.assertFalse(self.mgr.toggle_favourite(torx))
        self.assertEqual(self.mgr.list_icons(FAVOURITES), [])

    def test_recently_used_newest_first_and_limited(self):
        icons = self.mgr.list_icons()[: im.RECENT_LIMIT + 2]
        for icon in icons:
            self.mgr.mark_used(icon)
        self.mgr.mark_used(icons[0])
        recent = self.mgr.list_icons(RECENT)
        self.assertEqual(len(recent), im.RECENT_LIMIT)
        self.assertEqual(recent[0].key, icons[0].key)
        self.assertEqual(recent[1].key, icons[-1].key)

    def test_user_icon_metadata(self):
        item = self.mgr.save_user_icon(self._black_square(), "Drawer label")
        self.assertTrue(item.user)
        self.assertEqual(item.category, USER_CATEGORY)

        item = self.mgr.update_user_icon(item, "Kitchen drawer", "Tools", parse_keywords("Kök, la-da ,"))
        self.assertEqual(item.title, "Kitchen drawer")
        self.assertEqual(item.category, "Tools")
        self.assertEqual(item.keywords, ["kök", "la-da"])
        # Filed under Tools, still listed in My Icons, and found by its search words
        self.assertIn(item.key, [i.key for i in self.mgr.list_icons("Tools")])
        self.assertIn(item.key, [i.key for i in self.mgr.list_icons(USER_CATEGORY)])
        self.assertIn(item.key, [i.key for i in self.mgr.list_icons(search_query="kök")])

        # Survives a fresh scan, like the next start of the app
        again = IconManager(user_dir=self.user_dir).get_icon_by_path(item.file_path)
        self.assertEqual((again.title, again.category), ("Kitchen drawer", "Tools"))

    def test_unknown_category_falls_back_to_my_icons(self):
        item = self.mgr.save_user_icon(self._black_square(), "odd")
        item = self.mgr.update_user_icon(item, "Odd", "Engineering", [])
        self.assertEqual(item.category, USER_CATEGORY)

    def test_delete_user_icon(self):
        item = self.mgr.save_user_icon(self._black_square(), "gone")
        self.mgr.toggle_favourite(item)
        self.mgr.mark_used(item)
        self.assertTrue(self.mgr.delete_user_icon(item))
        self.assertFalse(os.path.exists(item.file_path))
        self.assertIsNone(self.mgr.get_icon_by_path(item.file_path))
        self.assertEqual(self.config.data["icon_favourites"], [])
        self.assertEqual(self.config.data["icon_recent"], [])

    def test_built_in_icons_cannot_be_changed(self):
        torx = self.mgr.get_icon_by_id("torx")
        self.assertFalse(self.mgr.delete_user_icon(torx))
        self.assertTrue(os.path.isfile(torx.file_path))
        self.assertIs(self.mgr.update_user_icon(torx, "x", "Tools", []), torx)

    def test_print_preview_is_black_and_white(self):
        preview = print_preview(self.mgr.get_icon_by_id("hex_nut").file_path)
        self.assertEqual(max(preview.size), im.PRINT_PREVIEW_DOTS)
        self.assertLessEqual({c for _, c in preview.getcolors()}, {0, 255})
        self.assertIsNone(print_preview(os.path.join(self.user_dir, "missing.png")))


if __name__ == "__main__":
    unittest.main()
