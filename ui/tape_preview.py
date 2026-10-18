#!/usr/bin/env python3
"""
WYSIWYG Tape Preview Canvas widget for Brother PT-P300BT.
Shows the label on a strip of tape with its cut lines, with zoom and a print-dot view.
"""

import tkinter as tk
import customtkinter as ctk
from PIL import Image, ImageTk
from typing import Optional, Tuple
from core.label_renderer import LabelMetrics

CANVAS_BG = "#1E1E1E"
CUT_LINE_COLOR = "#9E9E9E"
TAPE_LEAD_PX = 44  # Tape drawn before and after the label, so it reads as a strip


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

        self.canvas = tk.Canvas(self, bg=CANVAS_BG, highlightthickness=0, bd=0, height=150)
        self.canvas.pack(fill="both", expand=True, padx=10, pady=6)
        self.canvas.bind("<Configure>", lambda e: self._redraw())

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

    def update_content(
        self,
        preview_img: Image.Image,
        raster_img: Image.Image,
        metrics: LabelMetrics,
        tape_spec: Optional[dict] = None,
    ):
        """Updates the canvas with a newly rendered label and its metrics."""
        self._preview_image = preview_img
        self._raster_image = raster_img
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
        active_img = self._raster_image if self.view_mode == "raster" else self._preview_image
        if active_img is None:
            return

        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        if cw <= 10 or ch <= 10:
            return

        img_w, img_h = active_img.size
        lead = TAPE_LEAD_PX if self.view_mode == "tape" else 0

        if self.zoom_mode == "fit":
            max_w = max(cw - 2 * lead - 24, 80)
            max_h = max(ch - 28, 40)
            scale = max(min(max_w / img_w, max_h / img_h, 4.0), 0.4)
        else:
            scale = float(self.zoom_mode)

        disp_w = max(int(img_w * scale), 1)
        disp_h = max(int(img_h * scale), 1)

        if self.view_mode == "raster":
            resized = active_img.convert("RGB").resize((disp_w, disp_h), Image.Resampling.NEAREST)
        else:
            resized = active_img.resize((disp_w, disp_h), Image.Resampling.LANCZOS)

        x = max((cw - disp_w) // 2, lead + 12)
        y = max((ch - disp_h) // 2, 14)

        if self.view_mode == "tape":
            self._draw_tape_strip(x, y, disp_w, disp_h, active_img, scale)

        self._photo_ref = ImageTk.PhotoImage(resized)
        self.canvas.create_image(x, y, anchor="nw", image=self._photo_ref)

        if self.view_mode == "raster":
            self.canvas.create_rectangle(x - 1, y - 1, x + disp_w, y + disp_h, outline="#444444", width=1)
        else:
            self._draw_cut_lines(x, y, disp_w, disp_h)

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
