#!/usr/bin/env python3
"""
Headless GUI test for the text label editor, the print queue, and view switching.
"""

import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from ui.app import PrintLabelApp, VIEW_QUEUE, VIEW_SETTINGS, VIEW_TEMPLATES, VIEW_TEXT


def _add_text_label(app, text, **config):
    app.text_editor.delete("1.0", "end")
    app.text_editor.insert("1.0", text)
    for key, value in config.items():
        setattr(app.config, key, value)
    app._on_add_to_queue()
    app.update()


def test_gui_queue():
    app = PrintLabelApp()
    app.virtual_mode_var.set(True)
    app.update_idletasks()
    app.update()

    # Starts on the text label view with the settings panel showing
    assert app._view == VIEW_TEXT
    assert app.sidebar.active == VIEW_TEXT
    assert app.designer_panel.winfo_ismapped(), "Settings panel should show for text labels"
    assert app.btn_print.cget("text") == "Print"

    # Add three labels
    _add_text_label(app, "1. KITCHEN - BASIL", tape_bg_color="#FFFFFF", tape_fg_color="#000000")
    _add_text_label(app, "2. KITCHEN - PAPRIKA", tape_bg_color="#FDD835", tape_fg_color="#000000")
    _add_text_label(
        app,
        "3. KITCHEN - ROSEMARY",
        tape_bg_color="#FFFFFF",
        qr_enabled=True,
        qr_data="https://example.com/recipe/rosemary",
    )
    assert len(app.label_queue) == 3, f"Expected 3 items, got {len(app.label_queue)}"
    assert app.sidebar.buttons[VIEW_QUEUE].cget("text").endswith("3"), "Rail should show the queue count"

    # Queue view: whole-strip preview, one main button, no settings panel
    app.sidebar.buttons[VIEW_QUEUE].invoke()
    app.update()
    assert app._view == VIEW_QUEUE
    assert not app.designer_panel.winfo_ismapped(), "Settings panel should hide in the queue view"
    assert app._current_metrics.label_count == 3, "Queue view should preview the whole strip"
    saved_text = app.queue_saved_badge.cget("text")
    print("Queue Saved Badge:", saved_text)
    assert "50.0 mm" in saved_text, f"Expected 50.0 mm in badge, got: {saved_text}"
    assert app.btn_print.cget("text") == "Print queue (3)"
    assert app.btn_print.cget("state") == "normal"
    assert not app.btn_add_queue.winfo_ismapped(), "Add to queue should hide in the queue view"

    # Reorder: move item 1 down
    app._on_move_queue_item(0, 1)
    app.update()
    assert "PAPRIKA" in app.label_queue[0].text

    # Edit a queued label: opens the text editor with its text
    app._on_load_queue_item(0)
    app.update()
    loaded_text = app.text_editor.get("1.0", "end-1c")
    print(f"Loaded item into editor: '{loaded_text}', view: '{app._view}'")
    assert "PAPRIKA" in loaded_text, f"Expected PAPRIKA in text editor, got {loaded_text}"
    assert app._view == VIEW_TEXT
    assert app.btn_add_queue.winfo_ismapped(), "Add to queue should be back in the editor"
    assert app.action_frame.winfo_ismapped(), "Action bar must stay visible at the bottom"

    # Templates and Settings have nothing to print
    for view in (VIEW_TEMPLATES, VIEW_SETTINGS):
        app.sidebar.buttons[view].invoke()
        app.update()
        assert app._view == view
        assert not app.btn_print.winfo_ismapped(), f"Print should hide in the {view} view"
        assert not app.preview_widget.winfo_ismapped(), f"Preview should hide in the {view} view"

    # Applying a template opens it in the text editor
    first_template = next(iter(app.templates_view.cards))
    app._apply_preset_and_edit(first_template)
    app.update()
    assert app._view == VIEW_TEXT
    assert app.btn_print.winfo_ismapped()

    # Reset settings
    app.config.tape_bg_color = "#E53935"
    app.config.show_guides = True
    app._on_reset_settings(confirm=False)
    app.update()
    assert app.config.tape_bg_color == "#FFFFFF", "Tape background should reset to white"
    assert app.config.show_guides is False, "Guides should reset to False"
    assert app.config.auto_cut_hardware is True, "Auto-cut flag should stay at its default"
    assert app.config.cut_line is False, "Cut guide lines should be False for single labels"

    # Printer panel opens and closes from the chip
    app.printer_chip.invoke()
    app.update()
    assert app.printer_panel.winfo_ismapped()
    app._hide_printer_panel()
    app.update()
    assert not app.printer_panel.winfo_ismapped()

    # Optional: set PRINTLABEL_TEST_ARTIFACTS to a folder to keep preview images
    artifact_dir = os.environ.get("PRINTLABEL_TEST_ARTIFACTS", "")
    if app._current_preview and os.path.isdir(artifact_dir):
        out_img_path = os.path.join(artifact_dir, "batch_queue_tape_preview.png")
        app._current_preview.save(out_img_path)
        print(f"Saved preview to: {out_img_path}")

    app.destroy()
    print("SUCCESS: Headless GUI queue tests passed!")


if __name__ == "__main__":
    test_gui_queue()
