#!/usr/bin/env python3
"""
WYSIWYG Tape Preview Canvas widget for Brother PT-P300BT.
Shows the label on a strip of tape with its cut lines, with zoom and a print-dot view.
"""

import tkinter as tk
import customtkinter as ctk
from PIL import Image, ImageOps, ImageTk
from typing import Optional, Tuple
from core.label_renderer import LabelMetrics

CANVAS_BG = "#1E1E1E"
CUT_LINE_COLOR = "#9E9E9E"
TAPE_LEAD_PX = 44  # Tape drawn before and after the label, so it reads as a strip
EDGE_PAD_PX = 12  # Space between the tape strip and the canvas edge
WHEEL_STEP_PX = 60  # Horizontal scroll per mouse wheel notch


def _blend(rgb: Tuple[int, int, int], other: Tuple[int, int, int], amount: float) -> str:
    r, g, b = (int(c1 * (1 - amount) + c2 * amount) for c1, c2 in zip(rgb, other))
    return f"#{r:02x}{g:02x}{b:02x}"


class TapePreviewWidget(ctk.CTkFrame):
    """Preview canvas with zoom, a tape strip around the label, and a raster (print dots) view."""

    def __init__(self, master, **kwargs):
        super().__init__(master, corner_radius=10, **kwargs)

        self._preview_image: Optional[Image.Image] = None
        self._raster_image: Optional[Image.Image] = None
        self._metrics: Optional[LabelMetrics] = None
        self._tape_spec: Optional[dict] = None
        self._photo_ref: Optional[ImageTk.PhotoImage] = None
        # Where the label was last drawn (x, y, width, height), in canvas coordinates
        self.label_bounds: Optional[Tuple[int, int, int, int]] = None

        self.zoom_mode = "fit"  # "fit", "1.0", "1.5", "2.0", "3.0"
        self.view_mode = "tape"  # "tape" or "raster"

        self._setup_ui()

    def _setup_ui(self):
        self.toolbar = ctk.CTkFrame(self, fg_color="transparent")
        self.toolbar.pack(fill="x", padx=10, pady=(8, 2))

        self.title_label = ctk.CTkLabel(self.toolbar, text="Preview", font=ctk.CTkFont(size=13, weight="bold"))
        self.title_label.pack(side="left", padx=(4, 12))

        self.mode_seg = ctk.CTkSegmentedButton(
            self.toolbar, values=["Label", "Print dots"], command=self._on_mode_change, height=24
        )
        self.mode_seg.set("Label")
        self.mode_seg.pack(side="left")

        self.zoom_seg = ctk.CTkSegmentedButton(
            self.toolbar, values=["Fit", "100%", "150%", "200%", "300%"], command=self._on_zoom_change, height=24
        )
        self.zoom_seg.set("Fit")
        self.zoom_seg.pack(side="right")

        # Metrics are packed before the canvas so the canvas is what shrinks on small windows
        self.metrics_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.metrics_frame.pack(side="bottom", fill="x", padx=10, pady=(0, 8))

        # Canvas plus a horizontal scrollbar that only shows when the label is wider than the view
        self.canvas_frame = ctk.CTkFrame(self, fg_color=CANVAS_BG, corner_radius=0)
        self.canvas_frame.pack(fill="both", expand=True, padx=10, pady=6)
        self.canvas_frame.grid_rowconfigure(0, weight=1)
        self.canvas_frame.grid_columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(self.canvas_frame, bg=CANVAS_BG, highlightthickness=0, bd=0, height=150)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.canvas.bind("<Configure>", lambda e: self._redraw())

        self.h_scrollbar = ctk.CTkScrollbar(
            self.canvas_frame, orientation="horizontal", command=self.canvas.xview, height=14, fg_color=CANVAS_BG
        )
        self.h_scrollbar.grid(row=1, column=0, sticky="ew", padx=4, pady=(0, 2))
        self.h_scrollbar.grid_remove()
        self.canvas.configure(xscrollcommand=self.h_scrollbar.set)

        # Wheel (with or without Shift) and dragging pan a label that is wider than the view
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<Shift-MouseWheel>", self._on_wheel)
        self.canvas.bind("<Button-4>", lambda e: self._scroll_by(-WHEEL_STEP_PX))
        self.canvas.bind("<Button-5>", lambda e: self._scroll_by(WHEEL_STEP_PX))
        self.canvas.bind("<Shift-Button-4>", lambda e: self._scroll_by(-WHEEL_STEP_PX))
        self.canvas.bind("<Shift-Button-5>", lambda e: self._scroll_by(WHEEL_STEP_PX))
        self.canvas.bind("<ButtonPress-1>", self._on_drag_start)
        self.canvas.bind("<B1-Motion>", self._on_drag)

        self.length_label = ctk.CTkLabel(self.metrics_frame, text="", font=ctk.CTkFont(size=12, weight="bold"))
        self.length_label.pack(side="left", padx=4)
        self.used_label = ctk.CTkLabel(self.metrics_frame, text="", text_color=("gray40", "gray60"))
        self.used_label.pack(side="left", padx=8)
        # Kept for callers that read it; the print time is part of used_label
        self.time_label = self.used_label

        self.warning_label = ctk.CTkLabel(
            self.metrics_frame, text="", font=ctk.CTkFont(size=12, weight="bold"), text_color="#E63946"
        )
        self.warning_label.pack(side="right", padx=4)

    def _on_mode_change(self, value: str):
        self.view_mode = "raster" if value == "Print dots" else "tape"
        self._redraw()

    def _on_zoom_change(self, value: str):
        self.zoom_mode = {"Fit": "fit", "100%": "1.0", "150%": "1.5", "200%": "2.0", "300%": "3.0"}[value]
        self._redraw()

    @property
    def is_scrollable(self) -> bool:
        """True when the label is wider than the view, so it can be scrolled sideways."""
        return self.h_scrollbar.winfo_manager() == "grid"

    def _scroll_by(self, pixels: int):
        if not self.is_scrollable:
            return
        region_w = float(self.canvas.cget("scrollregion").split()[2])
        self.canvas.xview_moveto(self.canvas.xview()[0] + pixels / region_w)

    def _on_wheel(self, event):
        # Windows reports 120 per notch, macOS reports small deltas
        notches = event.delta / 120 if abs(event.delta) >= 120 else (1 if event.delta > 0 else -1)
        self._scroll_by(int(-notches * WHEEL_STEP_PX))

    def _on_drag_start(self, event):
        if self.is_scrollable:
            self.canvas.scan_mark(event.x, 0)

    def _on_drag(self, event):
        if self.is_scrollable:
            self.canvas.scan_dragto(event.x, 0, gain=1)

    def update_content(
        self,
        preview_img: Image.Image,
        raster_img: Image.Image,
        metrics: LabelMetrics,
        tape_spec: Optional[dict] = None,
    ):
        """Updates the canvas with a newly rendered label and its metrics."""
        self._preview_image = preview_img
        # The raster runs down the tape the way the printer feeds it; turn it back to read like the
        # label, so both views line up and a long label scrolls sideways in either
        self._raster_image = ImageOps.mirror(raster_img).rotate(90, expand=True)
        self._metrics = metrics
        self._tape_spec = tape_spec

        if metrics.label_count > 1:
            self.length_label.configure(
                text=f"{metrics.label_count} labels · {metrics.print_length_mm:.1f} mm"
            )
        else:
            self.length_label.configure(text=f"{metrics.print_length_mm:.1f} mm label")
        self.used_label.configure(
            text=f"{metrics.total_used_length_mm:.0f} mm of tape · about {max(metrics.print_duration_sec, 1):.0f} s to print"
        )
        self.warning_label.configure(text=metrics.warning or "")

        self._redraw()

    def _redraw(self):
        """Draws the label centred and scaled, on a strip of tape with cut lines at both ends."""
        self.canvas.delete("all")
        self.label_bounds = None
        active_img = self._raster_image if self.view_mode == "raster" else self._preview_image
        if active_img is None:
            self._set_scrollable(False, 0, 0)
            return

        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        if cw <= 10 or ch <= 10:
            return

        img_w, img_h = active_img.size
        lead = TAPE_LEAD_PX if self.view_mode == "tape" else 0

        if self.zoom_mode == "fit":
            # Always the whole label, however long, so Fit works as the overview
            max_w = max(cw - 2 * (lead + EDGE_PAD_PX), 20)
            max_h = max(ch - 28, 20)
            scale = min(max_w / img_w, max_h / img_h, 4.0)
        else:
            scale = float(self.zoom_mode)

        disp_w = max(int(img_w * scale), 1)
        disp_h = max(int(img_h * scale), 1)

        # A label wider than the view scrolls sideways; otherwise it is centred
        content_w = disp_w + 2 * (lead + EDGE_PAD_PX)
        scrollable = content_w > cw
        self._set_scrollable(scrollable, content_w, ch)

        if self.view_mode == "raster":
            resized = active_img.convert("RGB").resize((disp_w, disp_h), Image.Resampling.NEAREST)
        else:
            resized = active_img.resize((disp_w, disp_h), Image.Resampling.LANCZOS)

        x = lead + EDGE_PAD_PX if scrollable else max((cw - disp_w) // 2, lead + EDGE_PAD_PX)
        y = max((ch - disp_h) // 2, 14)
        self.label_bounds = (x, y, disp_w, disp_h)

        if self.view_mode == "tape":
            self._draw_tape_strip(x, y, disp_w, disp_h, active_img, scale)

        self._photo_ref = ImageTk.PhotoImage(resized)
        self.canvas.create_image(x, y, anchor="nw", image=self._photo_ref)

        if self.view_mode == "raster":
            self.canvas.create_rectangle(x - 1, y - 1, x + disp_w, y + disp_h, outline="#444444", width=1)
        else:
            self._draw_cut_lines(x, y, disp_w, disp_h)

    def _set_scrollable(self, scrollable: bool, content_w: int, ch: int):
        """Shows or hides the scrollbar, keeping the middle of the view in place across redraws."""
        self.canvas.configure(cursor="sb_h_double_arrow" if scrollable else "")
        if not scrollable:
            self.canvas.configure(scrollregion=(0, 0, max(self.canvas.winfo_width(), 1), max(ch, 1)))
            self.canvas.xview_moveto(0)
            if self.is_scrollable:
                self.h_scrollbar.grid_remove()
            return

        first, last = self.canvas.xview() if self.is_scrollable else (0.0, 0.0)
        middle = (first + last) / 2
        self.canvas.configure(scrollregion=(0, 0, content_w, ch))
        if not self.is_scrollable:
            self.h_scrollbar.grid()
            self.canvas.xview_moveto(0)  # Start at the beginning of the label
        else:
            visible = self.canvas.winfo_width() / content_w
            self.canvas.xview_moveto(max(middle - visible / 2, 0.0))

    def _draw_tape_strip(self, x: int, y: int, disp_w: int, disp_h: int, img: Image.Image, scale: float):
        """Unprinted tape before and after the label, dimmed so the label stands out."""
        try:
            tape_rgb = img.convert("RGB").getpixel((0, 0))
        except Exception:
            tape_rgb = (255, 255, 255)
        dim = _blend(tape_rgb, (30, 30, 30), 0.45)

        top, bottom = y, y + disp_h
        if self._tape_spec:
            # The rendered canvas is slightly taller than the tape; trim to the tape itself
            margin = (self._tape_spec["canvas_height"] - self._tape_spec["tape_height"]) / 2 * scale
            top, bottom = y + margin, y + disp_h - margin

        self.canvas.create_rectangle(x - TAPE_LEAD_PX, top, x, bottom, fill=dim, outline="")
        self.canvas.create_rectangle(x + disp_w, top, x + disp_w + TAPE_LEAD_PX, bottom, fill=dim, outline="")

    def _draw_cut_lines(self, x: int, y: int, disp_w: int, disp_h: int):
        ch = self.canvas.winfo_height()
        for cx in (x, x + disp_w):
            self.canvas.create_line(cx, y - 6, cx, y + disp_h + 6, fill=CUT_LINE_COLOR, dash=(4, 3))
        # Scissors under the end cut, kept inside the canvas
        self.canvas.create_text(
            x + disp_w, min(y + disp_h + 8, ch - 2), text="✂", anchor="n" if y + disp_h + 20 < ch else "s",
            fill=CUT_LINE_COLOR, font=("Segoe UI Symbol", 10),
        )
