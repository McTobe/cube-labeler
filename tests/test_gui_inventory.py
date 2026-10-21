#!/usr/bin/env python3
"""
Headless GUI test for the bin label editor and its queue integration.
"""

import importlib.util
import os
import sys
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# The GUI needs tkinter, which many Linux Pythons leave out
if importlib.util.find_spec("tkinter") is None:
    if __name__ == "__main__":
        print("SKIPPED: tkinter is not installed")
        sys.exit(0)
    raise unittest.SkipTest("tkinter is not installed")

from ui.inventory_tab import HardwareInventoryTab, KIND_PART, format_length, unformat_length

# Don't read or overwrite the user's remembered bin label while testing
HardwareInventoryTab._load_last_label = lambda self: None
HardwareInventoryTab.save_last_label = lambda self: None

from ui.app import PrintLabelApp, VIEW_BIN, VIEW_QUEUE
from core.inventory_renderer import FastenerLabelConfig, ComponentLabelConfig


def _type(entry, text):
    entry.delete(0, "end")
    entry.insert(0, text)


def test_length_formatting():
    assert format_length("30") == "x30"
    assert format_length(" 2.5 ") == "x2.5"
    assert format_length("Mixed") == "Mixed"
    assert format_length("x30") == "x30"
    assert unformat_length("x30") == "30"
    assert unformat_length("×12") == "12"
    assert unformat_length("Mixed") == "Mixed"


def test_gui_inventory():
    app = PrintLabelApp()
    app.virtual_mode_var.set(True)
    app.update_idletasks()
    app.update()

    # 1. Bin label view from the rail
    app.sidebar.buttons[VIEW_BIN].invoke()
    app.update()
    tab = app.inventory_tab_widget
    assert app._view == VIEW_BIN
    assert isinstance(app.config.inventory_config, FastenerLabelConfig)
    assert not app.designer_panel.winfo_ismapped(), "Text settings panel should hide for bin labels"
    assert not hasattr(tab, "preset_combo"), "Presets are gone"

    # 2. Fastener: size, name, two bins with plain numbers, Pozidriv
    tab.entry_thread.set("M4")
    tab.entry_cat.set("SCREWS")
    tab.mode_seg.set("Two")
    tab._on_bins_changed("Two")
    _type(tab.entry_len_dual_1, "30")
    _type(tab.entry_len_dual_2, "35")
    tab._on_drive_selected("PZ")
    _type(tab.entry_tool_size, "PZ2")
    tab._on_field_change()
    app.update()
    cfg = app.config.inventory_config
    assert (cfg.thread_size, cfg.category, cfg.compartment_mode) == ("M4", "SCREWS", "dual")
    assert (cfg.length_dual_1, cfg.length_dual_2) == ("x30", "x35"), "Numbers should print as x30"
    assert (cfg.tool_type, cfg.tool_size) == ("pozidriv", "PZ2")

    app._on_add_to_queue()
    app.update()
    assert len(app.label_queue) == 1

    # Drives print with the library picture unless "Simple icon" is ticked
    assert app.config.inventory_config.simple_drive_icon is False
    tab.chk_simple_icon.select()
    tab._on_simple_icon_toggled()
    assert app.config.inventory_config.simple_drive_icon is True
    tab.chk_simple_icon.deselect()
    tab._on_simple_icon_toggled()
    assert app.config.inventory_config.simple_drive_icon is False

    # Own icon via the Library…/File… buttons: the dropdown reads "Custom"; a built-in drive replaces it
    icon_path = os.path.join(BASE_DIR, "assets", "icons", "fasteners", "robertson.png")
    tab._set_tool_icon_path(icon_path)
    assert app.config.inventory_config.tool_type == "custom"
    assert tab.drive_combo.get() == "Custom"
    assert tab.chk_simple_icon.cget("state") == "disabled", "Simple icon only applies to built-in drives"
    assert tab.lbl_custom_tool_icon.cget("text") == "robertson.png"
    tab._on_drive_selected("PZ")
    assert app.config.inventory_config.tool_type == "pozidriv"
    assert app.config.inventory_config.custom_tool_icon_path is None
    assert tab.lbl_custom_tool_icon.cget("text") == ""

    # 3. Four bins, laid out as a 2×2 grid of boxes
    tab.mode_seg.set("Four")
    tab._on_bins_changed("Four")
    for entry, value in zip(
        (tab.entry_len_q1, tab.entry_len_q2, tab.entry_len_q3, tab.entry_len_q4), ("10", "12", "16", "20")
    ):
        _type(entry, value)
    tab._on_field_change()
    assert app.config.inventory_config.compartment_mode == "quad"
    assert app.config.inventory_config.length_quad_4 == "x20"

    # 4. One bin with text instead of a length, plus a note
    tab.mode_seg.set("One")
    tab._on_bins_changed("One")
    _type(tab.entry_len_single, "Mixed")
    _type(tab.entry_std_1, "sizes")
    tab._on_field_change()
    cfg = app.config.inventory_config
    assert (cfg.compartment_mode, cfg.length_single, cfg.standard_line1) == ("single", "Mixed", "sizes")

    # 5. Parts: name, part number, icon
    tab.kind_seg.set(KIND_PART)
    tab._on_kind_changed(KIND_PART)
    tab.entry_banner_b.set("BEARINGS")
    _type(tab.entry_spec_pri, "608ZZ")
    tab._on_part_icon_selected("Fuse")
    tab._on_field_change()
    app.update()
    part = app.config.inventory_config
    assert isinstance(part, ComponentLabelConfig)
    assert (part.category_banner, part.spec_primary, part.icon_type) == ("BEARINGS", "608ZZ", "fuse")

    app.btn_add_queue.invoke()
    app.update()
    assert len(app.label_queue) == 2

    # 6. Queue view, then edit the queued fastener: the form shows plain numbers again
    app.sidebar.buttons[VIEW_QUEUE].invoke()
    app.update()
    assert app.btn_print.cget("text") == "Print queue (2)"
    app._on_load_queue_item(0)
    app.update()
    assert app._view == VIEW_BIN
    assert tab.active_archetype == "fastener"
    assert tab.mode_seg.get() == "Two"
    assert tab.entry_len_dual_1.get() == "30"
    assert tab.drive_combo.get() == "PZ"

    # 7. Older labels: the "assortment" layout opens as one bin with a note
    tab.load_inventory_config(
        FastenerLabelConfig(compartment_mode="assortment", assortment_line1="Blandade", assortment_line2="sorter")
    )
    app.update()
    assert tab.mode_seg.get() == "One"
    assert (tab.entry_len_single.get(), tab.entry_std_1.get()) == ("Blandade", "sorter")

    # Optional: set PRINTLABEL_TEST_ARTIFACTS to a folder to keep preview images
    artifact_dir = os.environ.get("PRINTLABEL_TEST_ARTIFACTS", "")
    if os.path.isdir(artifact_dir):
        app._current_preview.save(os.path.join(artifact_dir, "test_gui_inventory.png"))

    print("SUCCESS: Headless GUI Hardware Inventory tests passed!")
    app.destroy()


if __name__ == "__main__":
    test_length_formatting()
    test_gui_inventory()
