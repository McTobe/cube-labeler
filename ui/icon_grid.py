#!/usr/bin/env python3
"""
The icon library's grid of tiles, drawn on one canvas.

A grid of customtkinter buttons took about two seconds to build for the whole library, since
every button draws its own rounded shapes on its own canvas. Drawing all tiles on a single
canvas and keeping the thumbnails between opens makes the library open almost at once.
"""

import os
import tkinter as tk
import tkinter.font as tkfont
from typing import Callable, Dict, List, Optional, Tuple

import customtkinter as ctk
from PIL import Image, ImageTk

TILE_BG = "#F5F5F5"
TILE_HOVER = "#E3E3E3"
TILE_SELECTED = "#1F6AA5"
TILE_TEXT = "#222222"
TILE_W = 122
TILE_H = 104
TILE_GAP = 12
THUMB_SIZE = 52
TITLE_MAX_CHARS = 20
RADIUS = 8

# Shrunk thumbnails, kept for the whole session: (path, modified time, size) -> picture
_thumbnails: Dict[Tuple[str, float, int], Image.Image] = {}


def thumbnail(path: str, size: int) -> Optional[Image.Image]:
    """The picture at `path` shrunk to fit `size`, read from disk only once per change."""
    try:
        key = (path, os.path.getmtime(path), size)
    except OSError:
        return None
    img = _thumbnails.get(key)
    if img is None:
        try:
            with Image.open(path) as src:
                img = src.convert("RGBA")
            img.thumbnail((size, size), Image.Resampling.LANCZOS)
        except Exception:
            return None
        _thumbnails[key] = img
    return img


def short_title(title: str, limit: int = TITLE_MAX_CHARS) -> str:
    """Cuts long names at the end so the start of the name always shows."""
    return title if len(title) <= limit else title[: limit - 1].rstrip() + "…"


class IconGrid(ctk.CTkFrame):
    """
    Scrollable tiles for a list of icons. Calls on_click(path) when a tile is clicked and
    on_double(path) when it is double-clicked.
    """

    def __init__(self, master, on_click: Callable[[str], None], on_double: Callable[[str], None], **kwargs):
        super().__init__(master, corner_radius=8, **kwargs)
        self._on_click = on_click
        self._on_double = on_double
        self._items: List = []
        self._selected: Optional[str] = None
        self._hover: Optional[int] = None
        self._shapes: List[int] = []
        self._photos: Dict[Tuple[str, int], ImageTk.PhotoImage] = {}
        self._message = ""
        self._columns = 0
        self._cell_w = 0
        self._layout_job = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0, yscrollincrement=20)
        self.canvas.grid(row=0, column=0, sticky="nsew", padx=(6, 0), pady=6)
        self.scrollbar = ctk.CTkScrollbar(self, command=self.canvas.yview)
        self.scrollbar.grid(row=0, column=1, sticky="ns", pady=6, padx=(0, 3))
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.bind("<Configure>", self._on_resized)
        self.canvas.bind("<Button-1>", self._clicked)
        self.canvas.bind("<Double-Button-1>", self._double_clicked)
        self.canvas.bind("<Motion>", self._moved)
        self.canvas.bind("<Leave>", lambda e: self._set_hover(None))
        # Wheel events go to the widget under the mouse, so the grid only scrolls when pointed at
        self.canvas.bind("<MouseWheel>", self._wheel)
        self.canvas.bind("<Button-4>", lambda e: self._scroll(-3))
        self.canvas.bind("<Button-5>", lambda e: self._scroll(3))

    # ----- Public -----

    @property
    def items(self) -> list:
        return self._items

    def show(self, items: list, message: str = ""):
        """Shows these icons, or `message` when there are none, from the top."""
        self._items = list(items)
        self._message = message
        self._hover = None
        self._draw_tiles()
        self.canvas.yview_moveto(0.0)

    def select(self, path: Optional[str]):
        """Outlines the tile of `path`, or no tile."""
        old = self._index_of(self._selected)
        self._selected = path
        if old is not None:
            self._paint(old)
        new = self._index_of(path)
        if new is not None:
            self._paint(new)

    def forget_pictures(self):
        """Reads every picture again on the next draw, after the user's icons changed."""
        self._photos.clear()

    # ----- Drawing -----

    def _set_appearance_mode(self, mode_string):
        super()._set_appearance_mode(mode_string)
        self._draw_tiles()

    def _set_scaling(self, *args, **kwargs):
        super()._set_scaling(*args, **kwargs)
        self._photos.clear()
        self._draw_tiles()

    def _scale(self) -> float:
        try:
            return ctk.ScalingTracker.get_widget_scaling(self)
        except Exception:
            return 1.0

    def _font(self, s: float) -> tkfont.Font:
        family = ctk.ThemeManager.theme.get("CTkFont", {}).get("family", "TkDefaultFont")
        # A negative size is in pixels, the way customtkinter scales its own fonts
        return tkfont.Font(root=self.canvas, family=family, size=-round(11 * s))

    def _photo(self, path: str, size: int) -> Optional[ImageTk.PhotoImage]:
        key = (path, size)
        photo = self._photos.get(key)
        if photo is None:
            img = thumbnail(path, size)
            if img is None:
                return None
            photo = ImageTk.PhotoImage(img, master=self.canvas)
            self._photos[key] = photo
        return photo

    def _on_resized(self, _event=None):
        if self._layout_job:
            self.after_cancel(self._layout_job)
        self._layout_job = self.after(40, self._relayout)

    def _relayout(self):
        self._layout_job = None
        if self._columns_for_width() != self._columns:
            self._draw_tiles()

    def _columns_for_width(self) -> int:
        s = self._scale()
        width = self.canvas.winfo_width()
        if width <= 1:
            return 4
        return max(1, int((width - TILE_GAP * s) // ((TILE_W + TILE_GAP) * s)))

    def _draw_tiles(self):
        c = getattr(self, "canvas", None)
        if c is None:
            return
        c.delete("all")
        self._shapes = []
        bg = self._apply_appearance_mode(self.cget("fg_color"))
        c.configure(bg=bg)

        s = self._scale()
        width = max(c.winfo_width(), 1)
        cols = self._columns_for_width()
        self._columns = cols
        gap = round(TILE_GAP * s / 2)
        # Tiles share the spare width so the grid fills the area
        self._cell_w = max(int(width // cols), round((TILE_W + TILE_GAP) * s)) if width > 1 else round((TILE_W + TILE_GAP) * s)
        cell_h = round((TILE_H + TILE_GAP) * s)
        thumb = round(THUMB_SIZE * s)
        font = self._font(s)
        text_colour = TILE_TEXT

        if not self._items:
            c.create_text(width / 2, 50 * s, text=self._message, fill="gray60", font=self._font(s * 14 / 11),
                          width=max(width - 40, 100))
            c.configure(scrollregion=(0, 0, width, 100 * s))
            return

        for idx, item in enumerate(self._items):
            row, col = divmod(idx, cols)
            x1, y1 = col * self._cell_w + gap, row * cell_h + gap
            x2, y2 = x1 + self._cell_w - 2 * gap, y1 + cell_h - 2 * gap
            self._shapes.append(self._round_rect(x1, y1, x2, y2, RADIUS * s, width=max(2, round(2 * s))))
            self._paint(idx)
            cx = (x1 + x2) / 2
            photo = self._photo(item.file_path, thumb)
            if photo is not None:
                c.create_image(cx, y1 + 8 * s + thumb / 2, image=photo)
            c.create_text(cx, y2 - 14 * s, text=short_title(item.title), fill=text_colour, font=font,
                          width=self._cell_w - 2 * gap - 8)
        rows = (len(self._items) + cols - 1) // cols
        c.configure(scrollregion=(0, 0, width, rows * cell_h))

    def _round_rect(self, x1, y1, x2, y2, r, **kwargs) -> int:
        points = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
                  x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
        return self.canvas.create_polygon(points, smooth=True, **kwargs)

    def _paint(self, idx: int):
        if idx >= len(self._shapes):
            return
        selected = self._items[idx].file_path == self._selected
        fill = TILE_HOVER if idx == self._hover else TILE_BG
        self.canvas.itemconfigure(self._shapes[idx], fill=fill, outline=TILE_SELECTED if selected else fill)

    # ----- Mouse -----

    def _index_at(self, event) -> Optional[int]:
        if not self._items or not self._cell_w:
            return None
        s = self._scale()
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        col, row = int(x // self._cell_w), int(y // round((TILE_H + TILE_GAP) * s))
        if col >= self._columns or x < 0 or y < 0:
            return None
        idx = row * self._columns + col
        return idx if idx < len(self._items) else None

    def _index_of(self, path: Optional[str]) -> Optional[int]:
        if path is None:
            return None
        for idx, item in enumerate(self._items):
            if item.file_path == path:
                return idx
        return None

    def _set_hover(self, idx: Optional[int]):
        if idx == self._hover:
            return
        old, self._hover = self._hover, idx
        if old is not None:
            self._paint(old)
        if idx is not None:
            self._paint(idx)
        self.canvas.configure(cursor="hand2" if idx is not None else "")

    def _moved(self, event):
        self._set_hover(self._index_at(event))

    def _clicked(self, event):
        idx = self._index_at(event)
        if idx is not None:
            self._on_click(self._items[idx].file_path)

    def _double_clicked(self, event):
        idx = self._index_at(event)
        if idx is not None:
            self._on_double(self._items[idx].file_path)

    def _wheel(self, event):
        step = -int(event.delta / 120) if abs(event.delta) >= 120 else (-1 if event.delta > 0 else 1)
        self._scroll(step * 3)

    def _scroll(self, units: int):
        if self.canvas.yview() != (0.0, 1.0):
            self.canvas.yview_scroll(units, "units")
