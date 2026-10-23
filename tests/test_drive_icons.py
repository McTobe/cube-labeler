#!/usr/bin/env python3
"""
Tests for drive icons on bin labels: library pictures by default, simple drawings on request.
"""

import os
import sys
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from core.inventory_renderer import (
    DRIVE_LIBRARY_ICONS,
    FastenerLabelConfig,
    InventoryRenderer,
    drive_library_icon,
    resolve_icon_path,
)
from ui.templates import config_from_dict, config_to_dict
from core.label_renderer import LabelConfig


class TestDriveIcons(unittest.TestCase):
    def setUp(self):
        self.renderer = InventoryRenderer()

    def test_every_drive_has_a_library_picture(self):
        for tool_type in ("internal_hex", "external_hex", "phillips", "pozidriv", "torx", "slotted"):
            self.assertIn(tool_type, DRIVE_LIBRARY_ICONS)
            self.assertTrue(drive_library_icon(tool_type), tool_type)

    def test_library_picture_is_the_default(self):
        cfg = FastenerLabelConfig(tool_type="pozidriv", tool_size="2")
        self.assertFalse(cfg.simple_drive_icon)
        library = self.renderer.render_fastener(cfg)
        as_custom = self.renderer.render_fastener(
            FastenerLabelConfig(tool_type="custom", custom_tool_icon_path=drive_library_icon("pozidriv"), tool_size="2")
        )
        self.assertEqual(library.tobytes(), as_custom.tobytes())

    def test_simple_icon_draws_the_shape(self):
        library = self.renderer.render_fastener(FastenerLabelConfig(tool_type="torx", tool_size="20"))
        simple = self.renderer.render_fastener(
            FastenerLabelConfig(tool_type="torx", tool_size="20", simple_drive_icon=True)
        )
        self.assertNotEqual(library.tobytes(), simple.tobytes())

    def test_simple_icon_survives_a_template_round_trip(self):
        cfg = LabelConfig(inventory_config=FastenerLabelConfig(tool_type="phillips", simple_drive_icon=True))
        loaded = config_from_dict(config_to_dict(cfg))
        self.assertTrue(loaded.inventory_config.simple_drive_icon)

    def test_templates_saved_before_library_icons_keep_the_drawn_icon(self):
        data = config_to_dict(LabelConfig(inventory_config=FastenerLabelConfig(tool_type="torx")))
        del data["inventory_config"]["simple_drive_icon"]
        self.assertTrue(config_from_dict(data).inventory_config.simple_drive_icon)


class TestSavedLibraryIcons(unittest.TestCase):
    """The packaged app's icon library moves to a new temporary folder on every start."""

    def test_path_from_an_earlier_run_is_found_again(self):
        old = r"C:\Users\tobe\AppData\Local\Temp\_MEI12345\assets\icons\fasteners\hex_bolt.png"
        self.assertEqual(resolve_icon_path(old), drive_library_icon("external_hex"))

    def test_icon_from_an_earlier_run_still_prints(self):
        renderer = InventoryRenderer()
        current = FastenerLabelConfig(tool_type="custom", custom_tool_icon_path=drive_library_icon("torx"), tool_size="")
        stale = FastenerLabelConfig(
            tool_type="custom",
            custom_tool_icon_path="/tmp/_MEI99/assets/icons/fasteners/torx.png",
            tool_size="",
        )
        self.assertEqual(renderer.render_fastener(stale).tobytes(), renderer.render_fastener(current).tobytes())

    def test_icon_that_moved_category_is_found(self):
        old = r"C:\Users\tobe\AppData\Local\Temp\_MEI12345\assets\icons\engineering\gear.png"
        found = resolve_icon_path(old)
        self.assertTrue(os.path.isfile(found))
        self.assertEqual(os.path.basename(found), "gear.png")

    def test_other_paths_are_left_alone(self):
        for path in (None, "", r"D:\pictures\missing.png", "/home/tobe/assets/icons/fasteners/nope.png"):
            self.assertEqual(resolve_icon_path(path), path)


if __name__ == "__main__":
    unittest.main()
