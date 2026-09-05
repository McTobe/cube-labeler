#!/usr/bin/env python3
"""
WYSIWYG Tape Preview Canvas widget for Brother PT-P300BT.
Provides real-time interactive preview with zoom, rulers, and raster inspection.
"""

import tkinter as tk
import customtkinter as ctk
from PIL import Image, ImageTk, ImageDraw
from typing import Optional
from core.label_renderer import LabelMetrics


class TapePreviewWidget(ctk.CTkFrame):
    """Interactive preview canvas with tape realism, zoom, and raster view."""

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)

        self._preview_image: Optional[Image.Image] = None
        self._raster_image: Optional[Image.Image] = None
        self._metrics: Optional[LabelMetrics] = None
        self._photo_ref: Optional[ImageTk.PhotoImage] = None

        self.zoom_mode = "fit"  # "fit", "1.0", "1.5", "2.0"
        self.view_mode = "tape"  # "tape" or "raster"

        self._setup_ui()

    def _setup_ui(self):
        # Top toolbar for preview controls
        self.toolbar = ctk.CTkFrame(self, fg_color="transparent")
        self.toolbar.pack(fill="x", padx=10, pady=(6, 4))

        # Title / Mode
        self.title_label = ctk.CTkLabel(
            self.toolbar,
            text="Tape Preview",
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self.title_label.pack(side="left", padx=(4, 15))

        # View Mode Switch (Tape vs Raster)
        self.mode_seg = ctk.CTkSegmentedButton(
            self.toolbar,
            values=["Tape View", "Raster View (128-dot)"],
            command=self._on_mode_change,
        )
        self.mode_seg.set("Tape View")
        self.mode_seg.pack(side="left", padx=5)

        # Zoom Segmented Button
        self.zoom_seg = ctk.CTkSegmentedButton(
            self.toolbar,
            values=["Fit", "100%", "150%", "200%"],
            command=self._on_zoom_change,
        )
        self.zoom_seg.set("Fit")
        self.zoom_seg.pack(side="right", padx=5)

        # Canvas Frame with dark/light adaptive background
        self.canvas_frame = ctk.CTkFrame(self, corner_radius=8, fg_color=("gray88", "gray17"))
        self.canvas_frame.pack(fill="both", expand=True, padx=10, pady=4)

        # Tkinter Canvas
        self.canvas = tk.Canvas(
            self.canvas_frame,
            bg="#1E1E1E",
            highlightthickness=0,
            bd=0,
            height=120,
        )
        self.canvas.pack(fill="both", expand=True, padx=6, pady=6)
        self.canvas.bind("<Configure>", lambda e: self._redraw())

        # Metrics Bar at bottom of canvas
        self.metrics_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.metrics_frame.pack(fill="x", padx=10, pady=(4, 6))

        self.length_label = ctk.CTkLabel(
            self.metrics_frame,
            text="Label Length: -- mm",
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        self.length_label.pack(side="left", padx=8)

        self.time_label = ctk.CTkLabel(
            self.metrics_frame,
            text="Print Time: -- s",
            font=ctk.CTkFont(size=12),
            text_color="gray",
        )
        self.time_label.pack(side="left", padx=8)

        self.used_label = ctk.CTkLabel(
            self.metrics_frame,
            text="Total Tape Used: -- mm",
            font=ctk.CTkFont(size=12),
            text_color="gray",
        )
        self.used_label.pack(side="left", padx=8)

        self.warning_label = ctk.CTkLabel(
            self.metrics_frame,
            text="",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#E63946",
        )
        self.warning_label.pack(side="right", padx=8)

    def _on_mode_change(self, value: str):
        self.view_mode = "raster" if "Raster" in value else "tape"
        self._redraw()

    def _on_zoom_change(self, value: str):
        if value == "Fit":
            self.zoom_mode = "fit"
        elif value == "100%":
            self.zoom_mode = "1.0"
        elif value == "150%":
            self.zoom_mode = "1.5"
        elif value == "200%":
            self.zoom_mode = "2.0"
        self._redraw()

    def update_content(
        self,
        preview_img: Image.Image,
        raster_img: Image.Image,
        metrics: LabelMetrics,
    ):
        """Updates the canvas with new rendered label and metrics."""
        self._preview_image = preview_img
        self._raster_image = raster_img
        self._metrics = metrics

        # Update metrics labels
        if metrics.label_count > 1:
            self.length_label.configure(
                text=f"Batch Length ({metrics.label_count} labels): {metrics.print_length_mm:.1f} mm ({metrics.print_length_in:.2f} in)"
            )
        else:
            self.length_label.configure(
                text=f"Label Length: {metrics.print_length_mm:.1f} mm ({metrics.print_length_cm:.1f} cm / {metrics.print_length_in:.2f} in)"
            )
        self.time_label.configure(text=f"Print Time: ~{metrics.print_duration_sec:.1f} s")
        
        if metrics.tape_saved_mm > 0:
            self.used_label.configure(
                text=f"Total Tape: {metrics.total_used_length_mm:.1f} mm  |  🎉 Saved: {metrics.tape_saved_mm:.1f} mm",
                text_color="#4CAF50",
            )
        else:
            self.used_label.configure(
                text=f"Total Tape: {metrics.total_used_length_mm:.1f} mm",
                text_color="gray",
            )

        if metrics.warning:
            self.warning_label.configure(text=f"⚠ {metrics.warning}")
        else:
            self.warning_label.configure(text="")

        self._redraw()

    def _redraw(self):
        """Draws the active image centered and scaled on canvas."""
        self.canvas.delete("all")
        active_img = self._raster_image if self.view_mode == "raster" else self._preview_image

        if active_img is None:
            return

        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        if cw <= 10 or ch <= 10:
            return

        # Determine target scaling factor
        img_w, img_h = active_img.size

        if self.zoom_mode == "fit":
            # Leave 40px margin horizontally and 30px vertically
            max_w = max(cw - 40, 100)
            max_h = max(ch - 30, 40)
            scale = min(max_w / img_w, max_h / img_h, 3.0)
            scale = max(scale, 0.4)
        else:
            scale = float(self.zoom_mode)

        disp_w = max(int(img_w * scale), 1)
        disp_h = max(int(img_h * scale), 1)

        # Scale image with crisp resampling
        if self.view_mode == "raster":
            resized = active_img.convert("RGB").resize((disp_w, disp_h), Image.Resampling.NEAREST)
        else:
            resized = active_img.resize((disp_w, disp_h), Image.Resampling.LANCZOS)

        # Center in canvas
        x = max((cw - disp_w) // 2, 20)
        y = max((ch - disp_h) // 2, 15)

        # Draw subtle tape drop shadow
        shadow_box = [x - 2, y + 2, x + disp_w + 3, y + disp_h + 4]
        self.canvas.create_rectangle(
            shadow_box[0], shadow_box[1], shadow_box[2], shadow_box[3],
            fill="#0A0A0A", outline="", width=0
        )

        # Render image
        self._photo_ref = ImageTk.PhotoImage(resized)
        self.canvas.create_image(x, y, anchor="nw", image=self._photo_ref)

        # Draw tape border box
        border_color = "#444444" if self.view_mode == "raster" else "#888888"
        self.canvas.create_rectangle(
            x - 1, y - 1, x + disp_w, y + disp_h,
            outline=border_color, width=1
        )

        # Draw subtle cut position marker above the edge
        if self.view_mode != "raster":
            self.canvas.create_text(
                x + disp_w - 2, max(y - 8, 4),
                text="✂ Cut", fill="#888888", font=("Segoe UI", 9)
            )
