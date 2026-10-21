#!/usr/bin/env python3
"""
Tests that the preview shows long labels in full at Fit, and scrolls sideways
at the fixed zoom levels when the label is wider than the view.
"""

import importlib.util
import os
import sys
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# The preview needs tkinter, which many Linux Pythons leave out
if importlib.util.find_spec("tkinter") is None:
    raise unittest.SkipTest("tkinter is not installed")

import tkinter as tk
import customtkinter as ctk

from core.label_renderer import LabelConfig, LabelRenderer
from ui.tape_preview import TAPE_LEAD_PX, TapePreviewWidget
from ui.templates import config_from_dict, load_preset

VIEW_SIZE = (600, 440)  # About the preview's size in the default window


class TestTapePreview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.root = ctk.CTk()
        except tk.TclError as e:
            raise unittest.SkipTest(f"No display: {e}")
        cls.root.geometry(f"{VIEW_SIZE[0]}x{VIEW_SIZE[1]}")
        cls.renderer = LabelRenderer()
        cls.long_label = cls.renderer.render(config_from_dict(load_preset("Cable Flag / Wrap")))
        cls.short_label = cls.renderer.render(LabelConfig(text="A1", tape_width_mm=12))

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        self.preview = TapePreviewWidget(self.root)
        self.preview.pack(fill="both", expand=True)
        self.root.update()

    def tearDown(self):
        self.preview.destroy()

    def _show(self, rendered, zoom="Fit"):
        preview_img, raster_img, _, metrics = rendered
        self.preview.zoom_seg.set(zoom)
        self.preview._on_zoom_change(zoom)
        self.preview.update_content(preview_img, raster_img, metrics)
        self.root.update()

    def test_cable_wrap_is_longer_than_the_view(self):
        # Guards the premise of the other tests
        self.assertGreater(self.long_label[0].width, VIEW_SIZE[0])

    def test_fit_shows_the_whole_long_label(self):
        self._show(self.long_label)
        x, _, width, _ = self.preview.label_bounds
        view_w = self.preview.canvas.winfo_width()
        # The label and the tape around it, cut lines included, are all inside the view
        self.assertGreaterEqual(x - TAPE_LEAD_PX, 0)
        self.assertLessEqual(x + width + TAPE_LEAD_PX, view_w)
        self.assertFalse(self.preview.is_scrollable)
        self.assertFalse(self.preview.h_scrollbar.winfo_ismapped())

    def test_fit_still_enlarges_short_labels(self):
        self._show(self.short_label)
        _, _, width, _ = self.preview.label_bounds
        self.assertGreater(width, self.short_label[0].width)
        self.assertFalse(self.preview.is_scrollable)

    def test_short_label_does_not_scroll_at_100(self):
        self._show(self.short_label, "100%")
        self.assertFalse(self.preview.is_scrollable)
        self.assertEqual(self.preview.canvas.xview(), (0.0, 1.0))

    def test_zoomed_long_label_scrolls_from_the_start(self):
        self._show(self.long_label, "300%")
        self.assertTrue(self.preview.is_scrollable)
        self.assertTrue(self.preview.h_scrollbar.winfo_ismapped())
        first, last = self.preview.canvas.xview()
        self.assertEqual(first, 0.0)
        self.assertLess(last, 1.0)

    def test_wheel_scrolls_sideways(self):
        self._show(self.long_label, "200%")
        start = self.preview.canvas.xview()[0]
        event = tk.Event()
        event.delta = -120  # One notch down scrolls towards the end of the label
        self.preview._on_wheel(event)
        self.root.update()
        self.assertGreater(self.preview.canvas.xview()[0], start)
        event.delta = 240
        self.preview._on_wheel(event)
        self.root.update()
        self.assertEqual(self.preview.canvas.xview()[0], 0.0)

    def test_drag_pans_the_label(self):
        self._show(self.long_label, "300%")
        event = tk.Event()
        event.x = 400
        self.preview._on_drag_start(event)
        event.x = 100  # Dragging left brings the end of the label into view
        self.preview._on_drag(event)
        self.root.update()
        self.assertGreater(self.preview.canvas.xview()[0], 0.0)

    def test_scroll_position_survives_a_redraw(self):
        self._show(self.long_label, "300%")
        self.preview.canvas.xview_moveto(0.4)
        before = self.preview.canvas.xview()
        # Typing re-renders the label; the view should not jump back to the start
        self.preview.update_content(*self._parts(self.long_label))
        self.root.update()
        after = self.preview.canvas.xview()
        self.assertAlmostEqual(before[0], after[0], places=2)

    def test_back_to_fit_removes_the_scrollbar(self):
        self._show(self.long_label, "300%")
        self.assertTrue(self.preview.is_scrollable)
        self._show(self.long_label, "Fit")
        self.assertFalse(self.preview.is_scrollable)
        self.assertFalse(self.preview.h_scrollbar.winfo_ismapped())
        self.assertEqual(self.preview.canvas.xview(), (0.0, 1.0))

    def test_print_dots_view_scrolls_too(self):
        self._show(self.long_label, "200%")
        self.preview._on_mode_change("Print dots")
        self.root.update()
        self.assertTrue(self.preview.is_scrollable)

    def test_print_dots_read_like_the_label(self):
        # The raster runs down the tape; the preview turns it back to label orientation
        preview_img, raster_img, _, _ = self.long_label
        self.assertGreater(raster_img.height, raster_img.width)
        self._show(self.long_label)
        self.assertEqual(self.preview._raster_image.width, preview_img.width)
        self.assertEqual(self.preview._raster_image.height, raster_img.width)

    @staticmethod
    def _parts(rendered):
        preview_img, raster_img, _, metrics = rendered
        return preview_img, raster_img, metrics


if __name__ == "__main__":
    unittest.main()
