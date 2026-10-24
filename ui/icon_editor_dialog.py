#!/usr/bin/env python3
"""
Icon editor for Cube Labeler: one window for importing a picture, redrawing it with an
AI service and editing one of the user's icons later.

The picture on the left is the original. The settings in the middle turn it into the icon
on the right, which can be touched up dot by dot. The original, the settings and the
touch-ups are saved with the icon, so it opens again exactly as it was left.
"""

import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Callable, Optional

import customtkinter as ctk
from PIL import Image, ImageTk

from core import icon_editor as ie
from core.icon_editor import DRAWING, OUTLINE, SILHOUETTE, IconEdit
from core.ai_generator import CUSTOM, DEFAULT_PRESET, PRESET_LABELS, current_provider, preset_mode
from core.config import config_manager
from core.icon_manager import USER_CATEGORY, IconItem, icon_manager, parse_keywords

MUTED = ("gray40", "gray60")
OK_GREEN = "#10B981"
BUSY_BLUE = "#38BDF8"
ERROR_RED = "#EF4444"
PICTURE_W, PICTURE_H = 320, 240
# Each touch-up cell is this many screen pixels before display scaling
CELL_PX = 5
PRINT_ZOOM = 2
RENDER_DELAY_MS = 70
UNDO_LIMIT = 30

IMAGE_TYPES = [("Pictures", "*.png;*.jpg;*.jpeg;*.bmp;*.webp;*.gif"), ("All files", "*.*")]

MODE_LABELS = {DRAWING: "Drawing", SILHOUETTE: "Silhouette", OUTLINE: "Outline"}
MODE_HINTS = {
    DRAWING: "Dark parts become ink. Best for icons, logos and drawings.",
    SILHOUETTE: "Like Drawing, with every enclosed gap filled for a solid shape, like the built-in icons.",
    OUTLINE: "Traces the edges of a photo. Best for photos of a part on a plain background.",
}
THICKNESS_LABELS = {"Thinner": -1, "Normal": 0, "Bold": 1, "Bolder": 2, "Heavy": 3}
TOOLS = ("Look", "Pencil", "Eraser")


def suggested_name(path: str) -> str:
    """A readable icon name from a file name: m3_hex-nut.png gives M3 hex nut."""
    stem = os.path.splitext(os.path.basename(path))[0]
    words = " ".join(stem.replace("_", " ").replace("-", " ").split())
    return words[:1].upper() + words[1:]


class IconEditorDialog(ctk.CTkToplevel):
    """
    Opens empty (make an icon), with a picture (import), with one of the user's icons
    (edit) or with a built-in icon (edit a copy). `on_saved(path, insert)` is called after
    saving; `insert` is True when the user pressed Save and insert.
    """

    def __init__(
        self,
        parent,
        on_saved: Optional[Callable[[str, bool], None]] = None,
        picture_path: Optional[str] = None,
        category: str = USER_CATEGORY,
        icon: Optional[IconItem] = None,
        can_insert: bool = True,
    ):
        super().__init__(parent)
        self.on_saved = on_saved
        # Opened from the Icons page there is no label to insert the icon into
        self._can_insert = can_insert
        # The user's icon being edited; built-in icons are edited as a new copy
        self.editing: Optional[IconItem] = icon if icon is not None and icon.user else None

        self.source: Optional[Image.Image] = None
        self.edit = IconEdit()
        self.touch = ie.new_touch_layer()
        self._undo: list = []
        self._base_mask: Optional[Image.Image] = None
        self._base_key = None
        self._result_mask: Optional[Image.Image] = None
        self._picture_before_ai: Optional[Image.Image] = None
        self._render_job = None
        self._crop_start = None
        self._picture_box = (0, 0, 1, 1)  # where the picture sits on its canvas: x, y, w, h
        self._dirty = False
        self._busy = False
        self._photo_refs = {}

        self.title("Edit icon" if self.editing else "Make an icon")
        self.geometry("1140x720")
        self.minsize(1060, 680)
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        try:
            scale = ctk.ScalingTracker.get_window_scaling(self)
        except Exception:
            scale = 1.0
        self._scale = max(1.0, scale)
        self._cell = max(CELL_PX, int(round(CELL_PX * self._scale)))

        self._build_ui()
        self.bind("<Control-v>", self._on_paste_key)
        self.bind("<Control-z>", lambda e: self._undo_touch())

        if icon is not None:
            self._load_icon(icon)
        elif picture_path:
            self._load_picture_file(picture_path)
        self.cat_menu.set(category if category in icon_manager.built_in_categories else USER_CATEGORY)
        if icon is not None:
            self.cat_menu.set(icon.category)
        self._sync_controls()
        self._render_now()
        self._dirty = False

    # ----- Layout -----

    def _build_ui(self):
        self.grid_columnconfigure(2, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, columnspan=3, sticky="ew", padx=16, pady=(12, 4))
        ctk.CTkLabel(header, text=self.title(), font=ctk.CTkFont(size=18, weight="bold")).pack(side="left")
        ctk.CTkLabel(
            header, text="Pick a picture, tune how it turns into black and white, then touch it up.",
            font=ctk.CTkFont(size=12), text_color=MUTED,
        ).pack(side="left", padx=12)

        left = ctk.CTkFrame(self, width=350)
        left.grid(row=1, column=0, sticky="nsw", padx=(16, 6), pady=6)
        middle = ctk.CTkScrollableFrame(self, width=250)
        middle.grid(row=1, column=1, sticky="nsw", padx=6, pady=6)
        right = ctk.CTkFrame(self)
        right.grid(row=1, column=2, sticky="nsew", padx=(6, 16), pady=6)

        self._build_picture_panel(left)
        self._build_settings_panel(middle)
        self._build_result_panel(right)

        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.grid(row=2, column=0, columnspan=3, sticky="ew", padx=16, pady=(4, 12))
        self.lbl_status = ctk.CTkLabel(bottom, text="", font=ctk.CTkFont(size=12), text_color=MUTED, anchor="w")
        self.lbl_status.pack(side="left", fill="x", expand=True)
        self.btn_save_insert = ctk.CTkButton(
            bottom, text="Save and insert", width=150, height=36, fg_color=OK_GREEN, hover_color="#059669",
            font=ctk.CTkFont(size=13, weight="bold"), command=lambda: self._save(insert=True),
        )
        if self._can_insert:
            self.btn_save_insert.pack(side="right", padx=(8, 0))
        self.btn_save = ctk.CTkButton(
            bottom, text="Save", width=110, height=36, font=ctk.CTkFont(size=13, weight="bold"),
            command=lambda: self._save(insert=False),
        )
        self.btn_save.pack(side="right", padx=(8, 0))
        ctk.CTkButton(
            bottom, text="Cancel", width=100, height=36, fg_color="gray30", hover_color="gray40", command=self._cancel,
        ).pack(side="right")

    def _section(self, parent, text: str, top: int = 10):
        ctk.CTkLabel(parent, text=text, font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", padx=10, pady=(top, 2))

    def _build_picture_panel(self, panel):
        self._section(panel, "Picture", top=8)
        w, h = int(PICTURE_W * self._scale), int(PICTURE_H * self._scale)
        self.picture_canvas = tk.Canvas(panel, width=w, height=h, bg="#D9D9D9", highlightthickness=0, cursor="crosshair")
        self.picture_canvas.pack(padx=10)
        self.picture_canvas.bind("<ButtonPress-1>", self._on_crop_press)
        self.picture_canvas.bind("<B1-Motion>", self._on_crop_drag)
        self.picture_canvas.bind("<ButtonRelease-1>", self._on_crop_release)
        self.picture_canvas.bind("<Double-Button-1>", lambda e: self._reset_crop())
        ctk.CTkLabel(
            panel, text="Drag on the picture to crop it. Double-click to show all of it.",
            font=ctk.CTkFont(size=11), text_color=MUTED,
        ).pack(anchor="w", padx=10)

        row = ctk.CTkFrame(panel, fg_color="transparent")
        row.pack(fill="x", padx=10, pady=(6, 0))
        ctk.CTkButton(row, text="Open picture…", width=150, command=self._open_picture).pack(side="left")
        ctk.CTkButton(row, text="Paste  (Ctrl+V)", width=150, fg_color="gray30", hover_color="gray40",
                      command=self._paste_picture).pack(side="right")

        ai = ctk.CTkFrame(panel)
        ai.pack(fill="x", padx=10, pady=(12, 10))
        self.lbl_ai_title = ctk.CTkLabel(ai, text="", font=ctk.CTkFont(size=12, weight="bold"))
        self.lbl_ai_title.pack(anchor="w", padx=8, pady=(6, 2))
        self.preset_menu = ctk.CTkOptionMenu(ai, values=PRESET_LABELS, height=28, command=self._on_preset)
        self.preset_menu.set(DEFAULT_PRESET)
        self.preset_menu.pack(fill="x", padx=8, pady=(0, 4))
        # Only shown for the Custom preset
        self.entry_custom = ctk.CTkEntry(
            ai, height=28, placeholder_text="Your instructions, e.g. front view, keep the two screw holes")
        self.entry_custom.bind("<Return>", lambda e: self._redraw_with_ai())
        self.btn_ai = ctk.CTkButton(ai, text="Redraw my picture", height=28, fg_color="#8B5CF6",
                                    hover_color="#7C3AED", command=self._redraw_with_ai)
        self.btn_ai.pack(fill="x", padx=8, pady=(0, 4))
        self.btn_restore = ctk.CTkButton(ai, text="Use my own picture again", height=26, fg_color="gray30",
                                         hover_color="gray40", command=self._restore_picture)
        self.lbl_key_note = ctk.CTkLabel(ai, text="", font=ctk.CTkFont(size=11), text_color=MUTED,
                                         wraplength=int(300 * self._scale), justify="left")
        self.lbl_key_note.pack(anchor="w", padx=8, pady=(0, 6))
        self._show_provider()

    def _show_provider(self):
        provider = current_provider()
        self.lbl_ai_title.configure(text=f"Redraw it with {provider.name}")
        if provider.api_key:
            note = f"Uses the {provider.name} API key from Settings."
        else:
            note = f"Needs your own {provider.name} API key, added under Settings in the main window."
            if provider.id == "gemini":
                note += " Or make the picture at gemini.google.com and open or paste it here."
        self.lbl_key_note.configure(text=note)

    def _on_preset(self, label: str):
        if label == CUSTOM:
            self.entry_custom.pack(fill="x", padx=8, pady=(0, 4), before=self.btn_ai)
            self.entry_custom.focus_set()
        else:
            self.entry_custom.pack_forget()

    def _build_settings_panel(self, panel):
        self._section(panel, "Read the picture as", top=4)
        self.seg_mode = ctk.CTkSegmentedButton(panel, values=list(MODE_LABELS.values()), command=self._on_mode)
        self.seg_mode.pack(fill="x", padx=10)
        self.lbl_mode_hint = ctk.CTkLabel(panel, text="", font=ctk.CTkFont(size=11), text_color=MUTED,
                                          wraplength=int(230 * self._scale), justify="left")
        self.lbl_mode_hint.pack(anchor="w", padx=10, pady=(2, 0))

        self._section(panel, "Darkness cutoff")
        self.sw_auto = ctk.CTkSwitch(panel, text="Automatic", command=self._on_auto_threshold)
        self.sw_auto.pack(anchor="w", padx=10)
        self.slider_threshold = ctk.CTkSlider(panel, from_=1, to=254, number_of_steps=253, command=self._on_threshold)
        self.slider_threshold.pack(fill="x", padx=10, pady=(4, 0))
        self.lbl_threshold = ctk.CTkLabel(panel, text="", font=ctk.CTkFont(size=11), text_color=MUTED)
        self.lbl_threshold.pack(anchor="w", padx=10)

        self.sw_invert = ctk.CTkSwitch(panel, text="Swap black and white", command=self._on_switches)
        self.sw_invert.pack(anchor="w", padx=10, pady=(8, 0))

        self._section(panel, "Line thickness")
        self.seg_thickness = ctk.CTkSegmentedButton(panel, values=list(THICKNESS_LABELS), command=self._on_thickness,
                                                    font=ctk.CTkFont(size=11))
        self.seg_thickness.pack(fill="x", padx=10)

        self._section(panel, "Clean up")
        self.sw_specks = ctk.CTkSwitch(panel, text="Remove specks", command=self._on_switches)
        self.sw_specks.pack(anchor="w", padx=10, pady=(0, 4))
        self.sw_fill = ctk.CTkSwitch(panel, text="Fill enclosed gaps", command=self._on_switches)
        self.sw_fill.pack(anchor="w", padx=10)

        self._section(panel, "Turn and mirror")
        row = ctk.CTkFrame(panel, fg_color="transparent")
        row.pack(fill="x", padx=10)
        ctk.CTkButton(row, text="⟲", width=52, command=lambda: self._turn(-1)).pack(side="left")
        ctk.CTkButton(row, text="⟳", width=52, command=lambda: self._turn(1)).pack(side="left", padx=6)
        ctk.CTkButton(row, text="Mirror", width=80, command=self._mirror).pack(side="left")

        ctk.CTkButton(panel, text="Reset settings", height=28, fg_color="gray30", hover_color="gray40",
                      command=self._reset_settings).pack(fill="x", padx=10, pady=(12, 0))


    def _build_result_panel(self, panel):
        top = ctk.CTkFrame(panel, fg_color="transparent")
        top.pack(fill="x", padx=10, pady=(8, 4))
        ctk.CTkLabel(top, text="Icon", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left")
        ctk.CTkButton(top, text="Clear touch-ups", width=110, height=26, fg_color="gray30", hover_color="gray40",
                      command=self._clear_touch).pack(side="right")
        ctk.CTkButton(top, text="Undo", width=60, height=26, fg_color="gray30", hover_color="gray40",
                      command=self._undo_touch).pack(side="right", padx=6)
        self.seg_tool = ctk.CTkSegmentedButton(top, values=list(TOOLS), command=self._on_tool)
        self.seg_tool.set(TOOLS[0])
        self.seg_tool.pack(side="right", padx=6)

        side = self._cell * ie.TOUCH_GRID
        self.icon_canvas = tk.Canvas(panel, width=side, height=side, bg="white", highlightthickness=1,
                                     highlightbackground="#9CA3AF")
        self.icon_canvas.pack(padx=10, pady=(0, 4))
        self.icon_canvas.bind("<ButtonPress-1>", lambda e: self._on_touch(e, start=True))
        self.icon_canvas.bind("<B1-Motion>", self._on_touch)
        self.icon_canvas.bind("<ButtonPress-3>", lambda e: self._on_touch(e, start=True, erase=True))
        self.icon_canvas.bind("<B3-Motion>", lambda e: self._on_touch(e, erase=True))
        self.icon_canvas.bind("<ButtonRelease-1>", lambda e: self._render_print_preview())
        self.icon_canvas.bind("<ButtonRelease-3>", lambda e: self._render_print_preview())
        self.lbl_tool_hint = ctk.CTkLabel(panel, text="", font=ctk.CTkFont(size=11), text_color=MUTED)
        self.lbl_tool_hint.pack(anchor="w", padx=10)

        row = ctk.CTkFrame(panel, fg_color="transparent")
        row.pack(fill="x", padx=10, pady=(4, 8))
        printed = ctk.CTkFrame(row, fg_color="transparent")
        printed.pack(side="left", anchor="n")
        dots = int(ie.PRINT_DOTS * PRINT_ZOOM * self._scale)
        self.print_canvas = tk.Canvas(printed, width=dots, height=dots, bg="white", highlightthickness=1,
                                      highlightbackground="#9CA3AF")
        self.print_canvas.pack(anchor="w")
        ctk.CTkLabel(
            printed, text="How it prints on a 12 mm\nbin label, dot for dot", font=ctk.CTkFont(size=11),
            text_color=MUTED, justify="left",
        ).pack(anchor="w")

        details = ctk.CTkFrame(row, fg_color="transparent")
        details.pack(side="left", fill="x", expand=True, padx=(14, 0), anchor="n")
        ctk.CTkLabel(details, text="Name", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w")
        self.entry_name = ctk.CTkEntry(details, placeholder_text="e.g. WAGO 221, M3 hex screw", height=28)
        self.entry_name.pack(fill="x")
        ctk.CTkLabel(details, text="Category", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", pady=(4, 0))
        self.cat_menu = ctk.CTkOptionMenu(details, values=[USER_CATEGORY] + icon_manager.built_in_categories, height=28)
        self.cat_menu.pack(fill="x")
        ctk.CTkLabel(details, text="Search words", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", pady=(4, 0))
        self.entry_keywords = ctk.CTkEntry(details, placeholder_text="Comma separated", height=28)
        self.entry_keywords.pack(fill="x")
        self._on_tool(TOOLS[0])

    # ----- Loading pictures -----

    def _set_source(self, image: Image.Image, name: str = "", keep_settings: bool = False):
        self.source = ie.prepare_original(image)
        if not keep_settings:
            self.edit = IconEdit()
        else:
            self.edit.crop = None
        self.touch = ie.new_touch_layer()
        self._undo.clear()
        self._base_key = None
        if name and not self.entry_name.get().strip():
            self.entry_name.insert(0, name)
        self._dirty = True
        self._sync_controls()
        self._render_now()

    def _load_picture_file(self, path: str) -> bool:
        try:
            with Image.open(path) as picked:
                picked.seek(0)
                image = picked.convert("RGBA")
        except Exception as e:
            messagebox.showerror("Open picture", f"Could not read that picture:\n{e}", parent=self)
            return False
        self._picture_before_ai = None
        self.btn_restore.pack_forget()
        self._set_source(image, suggested_name(path))
        self._status(f"Opened {os.path.basename(path)}")
        return True

    def _load_icon(self, icon: IconItem):
        try:
            original, edit, touch = icon_manager.edit_source(icon)
        except Exception as e:
            messagebox.showerror("Edit icon", f"Could not open this icon:\n{e}", parent=self)
            return
        self.source = ie.prepare_original(original)
        # A finished icon is already black and white, so a middle cutoff keeps it as it is
        self.edit = edit or IconEdit(threshold=128, remove_specks=False)
        self.touch = touch if touch is not None and touch.size == (ie.TOUCH_GRID, ie.TOUCH_GRID) else ie.new_touch_layer()
        if self.editing:
            self.entry_name.insert(0, icon.title)
            self.entry_keywords.insert(0, ", ".join(icon.keywords))
            if edit is None:
                self._status("This icon was saved before the editor kept originals, so it opens from the icon itself.")
        else:
            self.entry_name.insert(0, f"{icon.title} (my copy)")
            self.entry_keywords.insert(0, ", ".join(icon.keywords))

    def _open_picture(self):
        path = filedialog.askopenfilename(parent=self, title="Open a picture", filetypes=IMAGE_TYPES)
        if path:
            self._load_picture_file(path)

    def _on_paste_key(self, _event=None):
        # Ctrl+V in a text box pastes text there instead
        focused = self.focus_get()
        if isinstance(focused, (tk.Entry, tk.Text)):
            return None
        self._paste_picture()
        return "break"

    def _paste_picture(self):
        try:
            from PIL import ImageGrab
            data = ImageGrab.grabclipboard()
        except Exception:
            data = None
        if isinstance(data, list):
            files = [p for p in data if isinstance(p, str) and os.path.isfile(p)]
            if files:
                self._load_picture_file(files[0])
                return
            data = None
        if not isinstance(data, Image.Image):
            messagebox.showinfo("Paste", "There is no picture on the clipboard. Copy a picture or a picture file first.",
                                parent=self)
            return
        self._picture_before_ai = None
        self.btn_restore.pack_forget()
        self._set_source(data, "Pasted picture")
        self._status("Pasted a picture")

    # ----- Cropping on the picture -----

    def _canvas_to_share(self, x: float, y: float):
        bx, by, bw, bh = self._picture_box
        return (min(1.0, max(0.0, (x - bx) / bw)), min(1.0, max(0.0, (y - by) / bh)))

    def _on_crop_press(self, event):
        if self.source is None:
            return
        self._crop_start = self._canvas_to_share(event.x, event.y)

    def _on_crop_drag(self, event):
        if self._crop_start is None:
            return
        end = self._canvas_to_share(event.x, event.y)
        self._draw_crop_box((*self._crop_start, *end))

    def _on_crop_release(self, event):
        if self._crop_start is None:
            return
        end = self._canvas_to_share(event.x, event.y)
        crop = ie.normalise_crop((*self._crop_start, *end))
        self._crop_start = None
        if crop is None:
            # A click without a drag leaves the crop as it was
            self._draw_picture()
            return
        self.edit.crop = crop
        self._changed()

    def _reset_crop(self):
        if self.edit.crop is not None:
            self.edit.crop = None
            self._changed()

    def _draw_crop_box(self, crop):
        c = self.picture_canvas
        c.delete("crop")
        bx, by, bw, bh = self._picture_box
        x0, y0, x1, y1 = crop
        c.create_rectangle(bx + x0 * bw, by + y0 * bh, bx + x1 * bw, by + y1 * bh,
                           outline="#1F6AA5", width=2, dash=(4, 2), tags="crop")

    def _draw_picture(self):
        c = self.picture_canvas
        c.delete("all")
        cw, ch = int(c["width"]), int(c["height"])
        if self.source is None:
            c.create_text(cw // 2, ch // 2, text="Open or paste a picture to start.\nAn AI service can redraw it below.",
                          fill="#4B5563", justify="center", font=("Segoe UI", 11))
            return
        shown = ie.orient(self.source, self.edit)
        shown.thumbnail((cw - 8, ch - 8), Image.Resampling.LANCZOS)
        checker = Image.new("RGBA", shown.size, (255, 255, 255, 255))
        checker.alpha_composite(shown)
        photo = ImageTk.PhotoImage(checker.convert("RGB"))
        self._photo_refs["picture"] = photo
        x, y = (cw - shown.width) // 2, (ch - shown.height) // 2
        self._picture_box = (x, y, max(1, shown.width), max(1, shown.height))
        c.create_image(x, y, anchor="nw", image=photo)
        if self.edit.crop:
            # Dim what the crop leaves out
            bx, by, bw, bh = self._picture_box
            x0, y0, x1, y1 = self.edit.crop
            for box in ((bx, by, bx + bw, by + y0 * bh), (bx, by + y1 * bh, bx + bw, by + bh),
                        (bx, by + y0 * bh, bx + x0 * bw, by + y1 * bh), (bx + x1 * bw, by + y0 * bh, bx + bw, by + y1 * bh)):
                c.create_rectangle(*box, fill="#000000", stipple="gray50", outline="")
            self._draw_crop_box(self.edit.crop)

    # ----- Settings -----

    def _sync_controls(self):
        """Shows the current settings on the controls."""
        e = self.edit
        self.seg_mode.set(MODE_LABELS[e.mode])
        self.lbl_mode_hint.configure(text=MODE_HINTS[e.mode])
        if e.threshold is None:
            self.sw_auto.select()
            self.slider_threshold.configure(state="disabled")
        else:
            self.sw_auto.deselect()
            self.slider_threshold.configure(state="normal")
            self.slider_threshold.set(e.threshold)
        for switch, on in ((self.sw_invert, e.invert), (self.sw_specks, e.remove_specks), (self.sw_fill, e.fill_holes)):
            switch.select() if on else switch.deselect()
        self.sw_fill.configure(state="disabled" if e.mode == SILHOUETTE else "normal")
        label = next((k for k, v in THICKNESS_LABELS.items() if v == e.thickness), "Normal")
        self.seg_thickness.set(label)

    def _changed(self):
        self._dirty = True
        if self._render_job:
            self.after_cancel(self._render_job)
        self._render_job = self.after(RENDER_DELAY_MS, self._render_now)

    def _on_mode(self, label: str):
        self.edit.mode = next(m for m, l in MODE_LABELS.items() if l == label)
        self.lbl_mode_hint.configure(text=MODE_HINTS[self.edit.mode])
        self.sw_fill.configure(state="disabled" if self.edit.mode == SILHOUETTE else "normal")
        self._changed()

    def _on_auto_threshold(self):
        if self.sw_auto.get():
            self.edit.threshold = None
            self.slider_threshold.configure(state="disabled")
        else:
            current = ie.threshold_for(self.source, self.edit) if self.source is not None else 160
            self.edit.threshold = current
            self.slider_threshold.configure(state="normal")
            self.slider_threshold.set(current)
        self._changed()

    def _on_threshold(self, value):
        if self.edit.threshold is None:
            return
        self.edit.threshold = int(value)
        self.lbl_threshold.configure(text=f"Cutoff {self.edit.threshold}: lower keeps only the darkest parts")
        self._changed()

    def _on_switches(self):
        self.edit.invert = bool(self.sw_invert.get())
        self.edit.remove_specks = bool(self.sw_specks.get())
        self.edit.fill_holes = bool(self.sw_fill.get())
        self._changed()

    def _on_thickness(self, label: str):
        self.edit.thickness = THICKNESS_LABELS[label]
        self._changed()

    def _turn(self, quarter: int):
        self.edit.rotate = (self.edit.rotate + quarter) % 4
        # The crop was drawn on the picture as it was turned before
        self.edit.crop = None
        self._changed()

    def _mirror(self):
        self.edit.flip = not self.edit.flip
        self.edit.crop = None
        self._changed()

    def _reset_settings(self):
        self.edit = IconEdit()
        self._sync_controls()
        self._changed()

    # ----- Touch-ups -----

    def _on_tool(self, tool: str):
        hints = {
            "Look": "Pick Pencil or Eraser to fix single dots. Right-click erases with the pencil.",
            "Pencil": "Click or drag to add ink. Right-click erases. Ctrl+Z undoes.",
            "Eraser": "Click or drag to remove ink. Ctrl+Z undoes.",
        }
        self.lbl_tool_hint.configure(text=hints[tool])
        self.icon_canvas.configure(cursor="arrow" if tool == "Look" else "pencil")
        self._draw_icon()

    def _on_touch(self, event, start: bool = False, erase: bool = False):
        tool = self.seg_tool.get()
        if tool == "Look" or self.source is None:
            return
        x, y = event.x // self._cell, event.y // self._cell
        if not (0 <= x < ie.TOUCH_GRID and 0 <= y < ie.TOUCH_GRID):
            return
        if start:
            self._undo.append(self.touch.copy())
            del self._undo[:-UNDO_LIMIT]
        value = ie.TOUCH_ERASE if erase or tool == "Eraser" else ie.TOUCH_INK
        if self.touch.getpixel((x, y)) != value:
            self.touch.putpixel((x, y), value)
            self._dirty = True
            self._apply_touch()

    def _undo_touch(self):
        if self._undo:
            self.touch = self._undo.pop()
            self._apply_touch()
            self._render_print_preview()

    def _clear_touch(self):
        if self.touch.getbbox():
            self._undo.append(self.touch.copy())
            self.touch = ie.new_touch_layer()
            self._dirty = True
            self._apply_touch()
            self._render_print_preview()

    # ----- Rendering -----

    def _render_now(self):
        self._render_job = None
        self._draw_picture()
        if self.source is None:
            self._base_mask = None
            self._result_mask = None
        else:
            key = tuple(sorted(self.edit.to_dict().items(), key=lambda kv: kv[0]))
            key = repr(key)
            if key != self._base_key:
                self._base_mask = ie.ink_mask(self.source, self.edit)
                self._base_key = key
            self._result_mask = ie.apply_touch(self._base_mask, self.touch)
        if self.edit.threshold is None:
            auto = ie.threshold_for(self.source, self.edit) if self.source is not None else None
            self.lbl_threshold.configure(text=f"Automatic cutoff: {auto}" if auto is not None else "Automatic")
        self._draw_icon()
        self._render_print_preview()
        has_icon = self._result_mask is not None and ie.has_ink(self._result_mask)
        state = "normal" if has_icon else "disabled"
        self.btn_save.configure(state=state)
        self.btn_save_insert.configure(state=state)
        self.btn_ai.configure(state="normal" if self.source is not None and not self._busy else "disabled")

    def _apply_touch(self):
        if self._base_mask is None:
            return
        self._result_mask = ie.apply_touch(self._base_mask, self.touch)
        self._draw_icon()

    def _draw_icon(self):
        c = self.icon_canvas
        c.delete("all")
        side = self._cell * ie.TOUCH_GRID
        if self._result_mask is None:
            c.create_text(side // 2, side // 2, text="The icon appears here", fill="#6B7280", font=("Segoe UI", 11))
            return
        # Ink black on white, like the tape; touch-ups tinted while a touch-up tool is picked
        shown = Image.new("RGB", self._result_mask.size, "white")
        shown.paste((0, 0, 0), mask=self._result_mask)
        if self.seg_tool.get() != "Look" and self.touch.getbbox():
            big = self.touch.resize(self._result_mask.size, Image.Resampling.NEAREST)
            shown.paste((31, 106, 165), mask=big.point(lambda v: 255 if v == ie.TOUCH_INK else 0))
            shown.paste((252, 165, 165), mask=big.point(lambda v: 255 if v == ie.TOUCH_ERASE else 0))
        shown = shown.resize((side, side), Image.Resampling.NEAREST)
        photo = ImageTk.PhotoImage(shown)
        self._photo_refs["icon"] = photo
        c.create_image(0, 0, anchor="nw", image=photo)

    def _render_print_preview(self):
        c = self.print_canvas
        c.delete("all")
        if self._result_mask is None or not ie.has_ink(self._result_mask):
            return
        dots = ie.print_dots(ie.mask_to_icon(self._result_mask)).convert("RGB")
        zoom = int(PRINT_ZOOM * self._scale)
        dots = dots.resize((dots.width * zoom, dots.height * zoom), Image.Resampling.NEAREST)
        photo = ImageTk.PhotoImage(dots)
        self._photo_refs["print"] = photo
        size = int(c["width"])
        c.create_image((size - dots.width) // 2, (size - dots.height) // 2, anchor="nw", image=photo)

    def _status(self, text: str, color=MUTED):
        self.lbl_status.configure(text=text, text_color=color)

    # ----- AI redraw -----

    def _redraw_with_ai(self):
        if self.source is None or self._busy:
            return
        provider = current_provider()
        if not provider.api_key:
            extra = ("\n\nOr make the picture in Gemini on the web, then open or paste it here."
                     if provider.id == "gemini" else "")
            messagebox.showwarning(f"Add your {provider.name} API key",
                                   f"{provider.name} needs an API key. Add one under Settings in the main window."
                                   + extra, parent=self)
            return
        preset = self.preset_menu.get()
        custom = self.entry_custom.get().strip()
        if preset == CUSTOM and not custom:
            messagebox.showinfo("Custom instructions", "Type how the picture should be redrawn first.", parent=self)
            self.entry_custom.focus_set()
            return
        picture = self._picture_before_ai or self.source
        self._run_ai(provider.name, lambda: provider.redraw(picture, preset, custom))

    def _run_ai(self, service: str, generate: Callable[[], Image.Image]):
        """
        Runs an AI call on a worker thread. Tkinter is not thread-safe, so the worker only
        puts its result on a queue and the Tk main loop polls it.
        """
        results: "queue.Queue" = queue.Queue()

        def worker():
            try:
                results.put((True, generate()))
            except Exception as e:
                results.put((False, str(e)))

        def poll():
            if not self.winfo_exists():
                return
            try:
                ok, value = results.get_nowait()
            except queue.Empty:
                self.after(100, poll)
                return
            self._set_busy(False)
            if ok:
                self._on_ai_picture(value, service)
            else:
                self._status(f"{service} could not make the icon", ERROR_RED)
                messagebox.showerror(f"{service} could not make the icon", value, parent=self)

        self._set_busy(True)
        self._status(f"Asking {service} for an icon…", BUSY_BLUE)
        threading.Thread(target=worker, daemon=True).start()
        self.after(100, poll)

    def _set_busy(self, busy: bool):
        self._busy = busy
        self.btn_ai.configure(state="disabled" if busy or self.source is None else "normal")

    def _on_ai_picture(self, picture: Image.Image, service: str):
        if self.source is not None and self._picture_before_ai is None:
            self._picture_before_ai = self.source
        self._set_source(picture)
        self.edit = IconEdit(mode=preset_mode(self.preset_menu.get()))
        self._sync_controls()
        self._render_now()
        if self._picture_before_ai is not None:
            self.btn_restore.pack(fill="x", padx=8, pady=(0, 6), before=self.lbl_key_note)
        self._status(f"{service}'s icon is ready. Tune it or touch it up, then save.", OK_GREEN)

    def _restore_picture(self):
        if self._picture_before_ai is None:
            return
        picture = self._picture_before_ai
        self._picture_before_ai = None
        self.btn_restore.pack_forget()
        self._set_source(picture)
        self._status("Back to your own picture")

    # ----- Saving -----

    def _save(self, insert: bool):
        if self.source is None or self._result_mask is None or not ie.has_ink(self._result_mask):
            return
        name = self.entry_name.get().strip() or "My icon"
        category = self.cat_menu.get()
        keywords = parse_keywords(self.entry_keywords.get())
        icon_image = ie.mask_to_icon(self._result_mask)
        try:
            if self.editing:
                item = icon_manager.replace_user_icon(
                    self.editing, icon_image, name, category, keywords,
                    original=self.source, edit=self.edit, touch=self.touch,
                )
            else:
                item = icon_manager.save_user_icon(
                    icon_image, name, category=category, keywords=keywords,
                    original=self.source, edit=self.edit, touch=self.touch,
                )
        except OSError as e:
            messagebox.showerror("Save icon", f"The icon could not be saved:\n{e}", parent=self)
            return
        self._dirty = False
        path = item.file_path if item else None
        self.grab_release()
        self.destroy()
        if path and self.on_saved:
            self.on_saved(path, insert)

    def _cancel(self):
        if self._dirty and self.source is not None:
            if not messagebox.askyesno("Close the editor", "Close without saving this icon?", parent=self):
                return
        self.grab_release()
        self.destroy()
