#!/usr/bin/env python3
"""
Headless GUI test for the bin label editor, its presets, and queue integration.
"""

import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from ui.app import PrintLabelApp, VIEW_BIN, VIEW_QUEUE
from core.inventory_renderer import FastenerLabelConfig, ComponentLabelConfig
from ui.inventory_tab import MODE_LABELS


def test_gui_inventory():
    app = PrintLabelApp()
    app.virtual_mode_var.set(True)
    app.update_idletasks()
    app.update()

    # 1. Switch to the bin label view from the rail
    app.sidebar.buttons[VIEW_BIN].invoke()
    app.update()

    assert app._view == VIEW_BIN
    assert app.config.inventory_config is not None, "inventory_config should be active for bin labels"
    assert isinstance(app.config.inventory_config, FastenerLabelConfig), "Default should be FastenerLabelConfig"
    assert app.btn_print.winfo_ismapped() and app.btn_add_queue.winfo_ismapped()
    assert not app.designer_panel.winfo_ismapped(), "Text settings panel should hide for bin labels"

    # 2. Preset A2: socket cap, 2 bins
    app.inventory_tab_widget._on_preset_selected("A2")
    app.update()
    assert app.config.inventory_config.thread_size == "M3"
    assert app.config.inventory_config.compartment_mode == "dual"

    # Optional: set PRINTLABEL_TEST_ARTIFACTS to a folder to keep preview images
    artifact_dir = os.environ.get("PRINTLABEL_TEST_ARTIFACTS", "")
    if os.path.isdir(artifact_dir):
        app._current_preview.save(os.path.join(artifact_dir, "test_gui_inventory_a2.png"))

    app._on_add_to_queue()
    app.update()
    assert len(app.label_queue) == 1, f"Expected 1 item, got {len(app.label_queue)}"

    # 3. Preset B1: ball bearings
    app.inventory_tab_widget._on_preset_selected("B1")
    # Banner text depends on the user's label language setting
    expected_banner = app.inventory_tab_widget.presets["B1"].config.category_banner
    app.update()
    assert isinstance(app.config.inventory_config, ComponentLabelConfig)
    assert app.config.inventory_config.category_banner == expected_banner
    assert app.config.inventory_config.spec_primary == "608ZZ"

    # Add to queue via the action bar button
    app.btn_add_queue.invoke()
    app.update()
    assert len(app.label_queue) == 2, f"Expected 2 items, got {len(app.label_queue)}"

    # 4. Preset B2: WAGO
    app.inventory_tab_widget._on_preset_selected("B2")
    app.update()
    app._on_add_to_queue()
    app.update()
    assert len(app.label_queue) == 3, f"Expected 3 items, got {len(app.label_queue)}"

    # 5. Queue view
    app.sidebar.buttons[VIEW_QUEUE].invoke()
    app.update()
    saved_text = app.queue_saved_badge.cget("text")
    print("Queue Saved Badge:", saved_text)
    assert "50.0 mm" in saved_text
    assert app.btn_print.cget("text") == "Print queue (3)"

    if os.path.isdir(artifact_dir):
        app._current_preview.save(os.path.join(artifact_dir, "test_gui_inventory_queue_batch.png"))

    # 6. Edit queued item 2 (component B1): opens the bin label editor
    app._on_load_queue_item(1)
    app.update()
    assert app._view == VIEW_BIN
    assert app.inventory_tab_widget.active_archetype == "component"
    assert app.inventory_tab_widget.entry_banner_b.get() == expected_banner
    assert app.inventory_tab_widget.entry_spec_pri.get() == "608ZZ"

    # 7. Custom component icon
    custom_icon_path = os.path.join(artifact_dir, "scratch", "sample_custom_icon.png")
    if os.path.exists(custom_icon_path):
        app.inventory_tab_widget._set_comp_icon_path(custom_icon_path)
        app.update()
        assert app.config.inventory_config.icon_type == "custom"
        assert app.config.inventory_config.custom_icon_path == custom_icon_path

    # 8. Each layout button sets its compartment mode, and loading a preset shows it again
    tab = app.inventory_tab_widget
    tab._on_preset_selected("A2")
    app.update()
    for mode, label in MODE_LABELS.items():
        tab.mode_seg.set(label)
        tab._on_comp_mode_changed(label)
        app.update()
        assert app.config.inventory_config.compartment_mode == mode, (label, mode)
    tab._on_preset_selected("A2")
    app.update()
    assert tab.mode_seg.get() == MODE_LABELS["dual"]

    print("SUCCESS: Headless GUI Hardware Inventory tests passed!")
    app.destroy()


if __name__ == "__main__":
    test_gui_inventory()
