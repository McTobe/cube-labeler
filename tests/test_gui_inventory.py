#!/usr/bin/env python3
"""
Headless GUI test for V2 Hardware Inventory Tab, Catalog Presets, and Batch Queue Integration.
"""

import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from ui.app import PrintLabelApp
from core.inventory_renderer import FastenerLabelConfig, ComponentLabelConfig

def test_gui_inventory():
    app = PrintLabelApp()
    app.virtual_mode_var.set(True)
    app.update_idletasks()
    app.update()

    # 1. Switch to Hardware & Bins Studio Mode
    app.studio_mode_seg.set("🔩 Hardware & Bins Studio")
    app._on_studio_mode_changed("🔩 Hardware & Bins Studio")
    app.update()

    assert app.config.inventory_config is not None, "inventory_config should be active in Hardware & Bins Studio"
    assert isinstance(app.config.inventory_config, FastenerLabelConfig), "Default should be FastenerLabelConfig"
    assert app.design_bar_frame.winfo_manager() == "pack", "Design bar should be visible in Hardware Studio"

    # 2. Select Preset A2: Socket Cap 2-Bin (M3 x30 x35)
    app.inventory_tab_widget.preset_combo.set("A2: Socket Cap 2-Bin (M3 x30 x35)")
    app.inventory_tab_widget._on_preset_selected("A2: Socket Cap 2-Bin (M3 x30 x35)")
    app.update()

    assert app.config.inventory_config.thread_size == "M3"
    assert app.config.inventory_config.compartment_mode == "dual"

    # Save preview image
    artifact_dir = r"C:\Users\Tobia\.gemini\antigravity\brain\3fb00a9f-a78e-4343-83af-9edbb0a62f47"
    if os.path.isdir(artifact_dir):
        app._current_preview.save(os.path.join(artifact_dir, "test_gui_inventory_a2.png"))

    # Add to Queue
    app._on_add_to_queue()
    app.update()
    assert len(app.label_queue) == 1, f"Expected 1 item, got {len(app.label_queue)}"

    # 3. Select Preset B1: Ball Bearings (KULLAGER 608ZZ)
    app.inventory_tab_widget.preset_combo.set("B1: Ball Bearings (KULLAGER 608ZZ)")
    app.inventory_tab_widget._on_preset_selected("B1: Ball Bearings (KULLAGER 608ZZ)")
    app.update()

    assert isinstance(app.config.inventory_config, ComponentLabelConfig)
    assert app.config.inventory_config.category_banner == "KULLAGER"
    assert app.config.inventory_config.spec_primary == "608ZZ"

    if os.path.isdir(artifact_dir):
        app._current_preview.save(os.path.join(artifact_dir, "test_gui_inventory_b1.png"))

    # Add to Queue via the action bar button
    app.btn_add_queue.invoke()
    app.update()
    assert len(app.label_queue) == 2, f"Expected 2 items, got {len(app.label_queue)}"

    # 4. Add Preset B2: WAGO 221-413
    app.inventory_tab_widget.preset_combo.set("B2: WAGO 3-Way Splicing (WAGO 221-413)")
    app.inventory_tab_widget._on_preset_selected("B2: WAGO 3-Way Splicing (WAGO 221-413)")
    app.update()
    app._on_add_to_queue()
    app.update()
    assert len(app.label_queue) == 3, f"Expected 3 items, got {len(app.label_queue)}"

    # 5. Switch to Print Queue tab via mode bar button
    app._open_queue_tab()
    app.update()

    saved_text = app.queue_saved_badge.cget("text")
    print("Queue Saved Badge:", saved_text)
    assert "50.0 mm" in saved_text

    assert app.design_bar_frame.winfo_manager() == "", "Design bar should hide on Print Queue tab"
    assert app.queue_bar_frame.winfo_manager() == "pack", "Queue bar should show on Print Queue tab"

    # Verify batch chain preview
    if os.path.isdir(artifact_dir):
        app._current_preview.save(os.path.join(artifact_dir, "test_gui_inventory_queue_batch.png"))

    # 6. Test Loading Item #2 (Component B1) back into editor
    app._on_load_queue_item(1)
    app.update()

    assert app.studio_mode_seg.get() == "🔩 Hardware & Bins Studio", f"Expected mode '🔩 Hardware & Bins Studio', got '{app.studio_mode_seg.get()}'"
    assert app.inventory_tab_widget.active_archetype == "component"
    assert app.inventory_tab_widget.entry_banner_b.get() == "KULLAGER"
    assert app.inventory_tab_widget.entry_spec_pri.get() == "608ZZ"

    # 7. Test custom component icon
    custom_icon_path = os.path.join(artifact_dir, "scratch", "sample_custom_icon.png")
    if os.path.exists(custom_icon_path):
        app.inventory_tab_widget._set_comp_icon_path(custom_icon_path)
        app.update()
        assert app.config.inventory_config.icon_type == "custom"
        assert app.config.inventory_config.custom_icon_path == custom_icon_path

    print("SUCCESS: Headless GUI Hardware Inventory tests passed!")
    app.destroy()

if __name__ == "__main__":
    test_gui_inventory()
