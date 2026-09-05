#!/usr/bin/env python3
"""
Headless GUI test for Queue System & Tape Waste Reduction.
"""

import os
import sys
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from ui.app import PrintLabelApp
from core.label_renderer import LabelConfig

def test_gui_queue():
    app = PrintLabelApp()
    app.virtual_mode_var.set(True)
    app.update_idletasks()
    app.update()

    # 1. Add Label 1 to Queue
    app.text_editor.delete("1.0", "end")
    app.text_editor.insert("1.0", "1. KITCHEN - BASIL")
    app.config.tape_bg_color = "#FFFFFF"
    app.config.tape_fg_color = "#000000"
    app._on_add_to_queue()
    app.update()

    assert len(app.label_queue) == 1, f"Expected 1 item, got {len(app.label_queue)}"

    # 2. Add Label 2 to Queue
    app.text_editor.delete("1.0", "end")
    app.text_editor.insert("1.0", "2. KITCHEN - PAPRIKA")
    app.config.tape_bg_color = "#FDD835"  # Yellow tape
    app.config.tape_fg_color = "#000000"
    app._on_add_to_queue()
    app.update()

    assert len(app.label_queue) == 2, f"Expected 2 items, got {len(app.label_queue)}"

    # 3. Add Label 3 to Queue
    app.text_editor.delete("1.0", "end")
    app.text_editor.insert("1.0", "3. KITCHEN - ROSEMARY")
    app.config.tape_bg_color = "#FFFFFF"
    app.config.tape_fg_color = "#000000"
    app.config.qr_enabled = True
    app.config.qr_data = "https://example.com/recipe/rosemary"
    app._on_add_to_queue()
    app.update()

    assert len(app.label_queue) == 3, f"Expected 3 items, got {len(app.label_queue)}"

    # Switch to Print Queue view via top bar button
    app._open_queue_tab()
    app.update()

    # Verify metrics
    saved_text = app.queue_saved_badge.cget("text")
    print("Queue Saved Badge:", saved_text)
    assert "50.0 mm" in saved_text, f"Expected 50.0 mm in badge, got: {saved_text}"

    # Verify dynamic action bar switching to Queue Bar
    assert app.design_bar_frame.winfo_manager() == "", "Design bar should be hidden on Print Queue tab"
    assert app.queue_bar_frame.winfo_manager() == "pack", "Queue bar should be packed on Print Queue tab"
    assert app.btn_print_batch.cget("state") == "normal"
    assert "PRINT QUEUE" in app.btn_print_batch.cget("text")
    assert app.btn_clear_queue.cget("state") == "normal"
    assert app.btn_preview_mode.cget("state") == "normal"

    # Test Preview Chain toggle button
    app._toggle_preview_mode()
    app.update()
    print("Preview mode after toggle:", app._preview_mode)

    # Test Reordering (Move item 2 down)
    app._on_move_queue_item(0, 1)
    app.update()
    assert "PAPRIKA" in app.label_queue[0].text

    # Test Load button (Load queue item 0 into editor)
    app._on_load_queue_item(0)
    app.update()
    loaded_text = app.text_editor.get("1.0", "end-1c")
    print(f"Loaded item into editor: '{loaded_text}', active tab: '{app.tabview.get()}'")
    assert "PAPRIKA" in loaded_text, f"Expected PAPRIKA in text editor, got {loaded_text}"
    assert app.tabview.get() == "Text & Typography"

    # Verify action bar switched back to Design Bar
    assert app.design_bar_frame.winfo_manager() == "pack", "Design bar should be packed on Text & Typography tab"
    assert app.queue_bar_frame.winfo_manager() == "", "Queue bar should be hidden on Text & Typography tab"
    assert app.action_frame.winfo_ismapped(), "Action frame must remain mapped and visible at bottom"

    # Test Reset Settings button
    app.config.tape_bg_color = "#E53935"
    app.config.show_guides = True
    app._on_reset_settings()
    app.update()
    assert app.config.tape_bg_color == "#FFFFFF", "Tape background should reset to white"
    assert app.config.show_guides is False, "Guides should reset to False"
    assert app.config.auto_cut_hardware is True, "Hardware boundary marks should remain True"
    assert app.config.cut_line is False, "Cut guide lines should be False for single labels"

    # Save batch preview image to artifacts directory
    artifact_dir = r"C:\Users\Tobia\.gemini\antigravity\brain\3fb00a9f-a78e-4343-83af-9edbb0a62f47"
    if app._current_preview:
        out_img_path = os.path.join(artifact_dir, "batch_queue_tape_preview.png")
        app._current_preview.save(out_img_path)
        print(f"Saved batch queue preview to: {out_img_path}")

    app.destroy()
    print("SUCCESS: Headless GUI queue tests passed!")

if __name__ == "__main__":
    test_gui_queue()
