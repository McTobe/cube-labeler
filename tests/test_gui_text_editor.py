#!/usr/bin/env python3
"""
Headless GUI test for the text label editor's styling toolbar and frame option.
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

from ui.app import PrintLabelApp


def _text(app):
    return app.text_editor.get("1.0", "end-1c")


def _select(app, first, last):
    app.text_editor.tag_remove("sel", "1.0", "end")
    app.text_editor.tag_add("sel", first, last)


def test_gui_text_styling():
    app = PrintLabelApp()
    app.virtual_mode_var.set(True)
    app.update()
    tb = app.text_editor
    tb.delete("1.0", "end")
    tb.insert("1.0", "M3 SCREWS\n8 mm")

    # Bold on the selection, then off again with the same button
    _select(app, "1.0", "1.2")
    app.format_buttons["bold"].invoke()
    assert _text(app) == "**M3** SCREWS\n8 mm", _text(app)
    app.format_buttons["bold"].invoke()
    assert _text(app) == "M3 SCREWS\n8 mm", _text(app)

    # Ctrl+I works like the italic button
    _select(app, "2.0", "2.1")
    tb.event_generate("<Control-i>")
    app.update()
    assert _text(app) == "M3 SCREWS\n*8* mm", _text(app)

    # Line size and alignment act on every selected line, and the menus follow the cursor
    _select(app, "1.0", "2.end")
    app._on_line_size_changed("Large")
    assert _text(app) == "# M3 SCREWS\n# *8* mm", _text(app)
    tb.tag_remove("sel", "1.0", "end")
    tb.mark_set("insert", "2.0")
    app._on_line_size_changed("Small")
    app._on_line_align_changed("Right")
    assert _text(app) == "# M3 SCREWS\n-# >> *8* mm", _text(app)
    app._sync_line_style_menus()
    assert app.line_size_menu.get() == "Small" and app.line_align_menu.get() == "Right"

    # Add column puts a divider line after the cursor's line
    tb.mark_set("insert", "1.3")
    app._on_add_column()
    assert _text(app).splitlines()[1] == "---"

    # Frame goes into the config and comes back from it
    app._on_frame_changed("Rounded")
    assert app.config.frame == "rounded"
    app._on_reset_settings(confirm=False)
    assert app.config.frame == "none" and app.frame_seg.get() == "None"

    # The styled label renders and its queue entry shows the text without markers
    app._trigger_render()
    app.update()
    app._on_add_to_queue()
    app.update()
    title, _ = app._queue_item_summary(app.label_queue[-1])
    assert title == "M3 SCREWS", title

    app.destroy()
    print("SUCCESS: Headless GUI text styling tests passed!")


if __name__ == "__main__":
    test_gui_text_styling()
