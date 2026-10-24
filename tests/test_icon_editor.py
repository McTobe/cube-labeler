#!/usr/bin/env python3
"""
Tests for the icon editor core: turning pictures into icons, the settings kept with them,
touch-ups and keeping originals so the user's icons can be edited again.
"""

import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from core import icon_editor as ie
from core import icon_manager as im
from core.icon_editor import DRAWING, OUTLINE, SILHOUETTE, IconEdit
from core.icon_manager import IconManager


def ring(size=(300, 200), bg="white", ink="black", width=16):
    img = Image.new("RGB", size, bg)
    ImageDraw.Draw(img).ellipse((60, 20, 240, 180), outline=ink, width=width)
    return img


def ink_count(mask):
    return sum(1 for v in mask.tobytes() if v)


class TestIconEdit(unittest.TestCase):
    def test_round_trip(self):
        edit = IconEdit(mode=OUTLINE, threshold=90, invert=True, crop=(0.1, 0.2, 0.8, 0.9),
                        rotate=3, flip=True, thickness=2, remove_specks=False, fill_holes=True)
        self.assertEqual(IconEdit.from_dict(edit.to_dict()), edit)

    def test_broken_settings_fall_back(self):
        edit = IconEdit.from_dict({"mode": "sketch", "threshold": 999, "rotate": 6, "crop": [1, 1, 1, 1], "x": 1})
        self.assertEqual((edit.mode, edit.threshold, edit.rotate, edit.crop), (DRAWING, 254, 2, None))
        self.assertEqual(IconEdit.from_dict(None), IconEdit())
        self.assertEqual(IconEdit.from_dict({"thickness": "lots"}), IconEdit())

    def test_crop_is_sorted(self):
        self.assertEqual(ie.normalise_crop((0.9, 0.8, 0.1, 0.2)), (0.1, 0.2, 0.9, 0.8))
        self.assertIsNone(ie.normalise_crop((0, 0, 1, 1)))


class TestRendering(unittest.TestCase):
    def test_drawing_is_centred_and_square(self):
        mask = ie.ink_mask(ring(), IconEdit())
        self.assertEqual(mask.size, (ie.ICON_SIZE, ie.ICON_SIZE))
        x0, y0, x1, y1 = mask.getbbox()
        self.assertAlmostEqual((x0 + x1) / 2, ie.ICON_SIZE / 2, delta=3)
        self.assertAlmostEqual((y0 + y1) / 2, ie.ICON_SIZE / 2, delta=3)
        # The ring stays a ring: its middle is empty
        self.assertEqual(mask.getpixel((128, 128)), 0)

    def test_silhouette_fills_the_middle(self):
        mask = ie.ink_mask(ring(), IconEdit(mode=SILHOUETTE))
        self.assertEqual(mask.getpixel((128, 128)), 255)
        filled = ie.ink_mask(ring(), IconEdit(fill_holes=True))
        self.assertEqual(filled.getpixel((128, 128)), 255)

    def test_dark_background_is_flipped(self):
        light = ie.ink_mask(ring(), IconEdit())
        dark = ie.ink_mask(ring(bg="black", ink="white"), IconEdit())
        self.assertLess(abs(ink_count(light) - ink_count(dark)), ink_count(light) * 0.05)
        swapped = ie.ink_mask(ring(), IconEdit(invert=True))
        self.assertGreater(ink_count(swapped), ink_count(light))

    def test_automatic_cutoff_handles_grey_pictures(self):
        # Mid grey ink on light grey would vanish with a fixed dark cutoff
        grey = ring(bg=(200, 200, 200), ink=(140, 140, 140))
        self.assertTrue(ie.has_ink(ie.ink_mask(grey, IconEdit())))
        self.assertGreater(ie.auto_threshold(grey.convert("L")), 140)
        self.assertFalse(ie.has_ink(ie.ink_mask(grey, IconEdit(threshold=60))))

    def test_thickness_changes_printed_lines(self):
        normal = ink_count(ie.ink_mask(ring(width=6), IconEdit()))
        bold = ink_count(ie.ink_mask(ring(width=6), IconEdit(thickness=2)))
        thin = ink_count(ie.ink_mask(ring(width=16), IconEdit(thickness=-1)))
        self.assertGreater(bold, normal * 1.3)
        self.assertLess(thin, ink_count(ie.ink_mask(ring(width=16), IconEdit())))

    def test_specks_are_removed(self):
        img = ring()
        draw = ImageDraw.Draw(img)
        for x in range(10, 290, 23):
            draw.point((x, 195), fill="black")
        draw.rectangle((5, 5, 6, 6), fill="black")
        clean = ie.ink_mask(img, IconEdit())
        noisy = ie.ink_mask(img, IconEdit(remove_specks=False))
        self.assertLess(ink_count(clean), ink_count(noisy))

    def test_crop_rotate_and_mirror(self):
        img = Image.new("RGB", (200, 100), "white")
        draw = ImageDraw.Draw(img)
        draw.rectangle((10, 10, 40, 90), fill="black")   # tall bar on the left
        draw.rectangle((120, 40, 190, 60), fill="black")  # wide bar on the right
        left = ie.ink_mask(img, IconEdit(crop=(0, 0, 0.4, 1)))
        x0, y0, x1, y1 = left.getbbox()
        self.assertGreater(y1 - y0, x1 - x0)
        turned = ie.ink_mask(img, IconEdit(rotate=1, crop=(0, 0, 1, 0.4)))
        x0, y0, x1, y1 = turned.getbbox()
        self.assertGreater(x1 - x0, y1 - y0)
        mirrored = ie.orient(img, IconEdit(flip=True))
        self.assertEqual(mirrored.getpixel((185, 50)), (0, 0, 0))

    def test_outline_traces_a_photo(self):
        photo = Image.new("RGB", (300, 200), (210, 205, 190))
        ImageDraw.Draw(photo).rectangle((80, 50, 220, 150), fill=(90, 60, 40))
        mask = ie.ink_mask(photo, IconEdit(mode=OUTLINE))
        self.assertTrue(ie.has_ink(mask))
        self.assertEqual(mask.getpixel((128, 128)), 0)  # only the edges, not the solid block

    def test_blank_picture_gives_no_ink(self):
        self.assertFalse(ie.has_ink(ie.ink_mask(Image.new("RGB", (50, 50), "white"), IconEdit())))

    def test_touch_ups(self):
        mask = ie.ink_mask(ring(), IconEdit())
        touch = ie.new_touch_layer()
        touch.putpixel((32, 32), ie.TOUCH_INK)  # the empty middle of the ring
        x0, y0, _, _ = mask.getbbox()
        touch.putpixel((x0 // 4, 32), ie.TOUCH_ERASE)
        out = ie.apply_touch(mask, touch)
        self.assertEqual(out.getpixel((130, 130)), 255)
        self.assertEqual(out.getpixel((x0 // 4 * 4 + 1, 130)), 0)
        self.assertIs(ie.apply_touch(mask, ie.new_touch_layer()), mask)

    def test_icon_and_print_preview(self):
        icon = ie.render_icon(ring(), IconEdit())
        self.assertEqual(icon.mode, "RGBA")
        self.assertEqual(icon.getpixel((0, 0))[3], 0)
        dots = ie.print_dots(icon)
        self.assertEqual(max(dots.size), ie.PRINT_DOTS)
        self.assertEqual(ie.icon_to_mask(icon).getbbox(), ie.mask_to_icon(ie.icon_to_mask(icon)).getbbox())


class FakeConfig:
    def __init__(self):
        self.data = {}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value


class TestKeptOriginals(unittest.TestCase):
    def setUp(self):
        self.user_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.user_dir, True)
        self.config = FakeConfig()
        patcher = patch.object(im, "config_manager", self.config)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.mgr = IconManager(user_dir=self.user_dir)

    def _save(self):
        original = ring(size=(1600, 1000))
        edit = IconEdit(mode=SILHOUETTE, thickness=1)
        touch = ie.new_touch_layer()
        touch.putpixel((3, 3), ie.TOUCH_INK)
        icon = ie.render_icon(original, edit, touch)
        return self.mgr.save_user_icon(icon, "Brass ring", category="Fasteners", keywords=["ring"],
                                       original=original, edit=edit, touch=touch)

    def test_original_settings_and_touch_ups_come_back(self):
        item = self._save()
        self.assertEqual((item.title, item.category, item.keywords), ("Brass ring", "Fasteners", ["ring"]))
        self.assertEqual(os.path.basename(item.file_path), "Brass_ring.png")
        original, edit, touch = self.mgr.edit_source(item)
        self.assertEqual(max(original.size), ie.ORIGINAL_MAX)
        self.assertEqual((edit.mode, edit.thickness), (SILHOUETTE, 1))
        self.assertEqual(touch.getpixel((3, 3)), ie.TOUCH_INK)
        # The originals folder is not taken for icons of its own
        self.assertEqual([i.id for i in self.mgr.list_icons(im.USER_CATEGORY)], ["Brass_ring"])

    def test_replace_keeps_file_name_and_favourite(self):
        item = self._save()
        self.mgr.toggle_favourite(item)
        new = ie.render_icon(ring(width=30), IconEdit())
        updated = self.mgr.replace_user_icon(item, new, "Ring", "Fasteners", [], original=ring(width=30), edit=IconEdit())
        self.assertEqual(updated.file_path, item.file_path)
        self.assertTrue(self.mgr.is_favourite(updated))
        _, edit, touch = self.mgr.edit_source(updated)
        self.assertEqual(edit.mode, DRAWING)
        self.assertIsNone(touch)

    def test_renaming_keeps_settings(self):
        item = self._save()
        self.mgr.update_user_icon(item, "Renamed", "Symbols", ["x"])
        self.assertIsNotNone(self.mgr.edit_source(self.mgr.get_icon_by_path(item.file_path))[1])

    def test_delete_removes_original(self):
        item = self._save()
        self.mgr.delete_user_icon(item)
        self.assertEqual(os.listdir(os.path.join(self.user_dir, im.ORIGINALS_DIR)), [])

    def test_icons_without_original_open_from_the_icon(self):
        item = self.mgr.save_user_icon(Image.new("RGBA", (64, 64), (0, 0, 0, 255)), "Old icon")
        original, edit, touch = self.mgr.edit_source(item)
        self.assertIsNone(edit)
        self.assertIsNone(touch)
        self.assertEqual(original.size, (64, 64))
        built_in = self.mgr.get_icon_by_id("torx")
        self.assertIsNone(self.mgr.edit_source(built_in)[1])


if __name__ == "__main__":
    unittest.main()
