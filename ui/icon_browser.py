#!/usr/bin/env python3
"""
Interactive Icon Browser Dialog for Brother PT-P300BT Label Studio.
Provides category filtering, search, thumbnail grid, and integration
with the AI Wireframe Generator.
"""

import os
import sys
import subprocess
import tkinter as tk
from typing import Callable, Optional, List, Dict
import customtkinter as ctk
from PIL import Image

from core.icon_manager import icon_manager, IconItem
from core.config import config_manager

TILE_BG = "#F5F5F5"
TILE_HOVER = "#E3E3E3"
TILE_SELECTED = "#1F6AA5"
TITLE_MAX_CHARS = 22


class IconBrowserDialog(ctk.CTkToplevel):
    """Modal dialog allowing users to browse, search, and select icons."""

    def __init__(
        self,
        parent,
        on_select: Callable[[str], None],
        initial_category: str = "All",
        title_suffix: str = "",
        on_open_ai_generator: Optional[Callable[[], None]] = None,
    ):
        super().__init__(parent)
        self.on_select_callback = on_select
        self.on_open_ai_generator = on_open_ai_generator
        self.selected_icon: Optional[IconItem] = None
        self._ctk_image_cache: Dict[str, ctk.CTkImage] = {}

        dialog_title = "📚 Icon Library"
        if title_suffix:
            dialog_title += f" - {title_suffix}"
        self.title(dialog_title)
        self.geometry("820x640")
        self.minsize(700, 500)

        # Make modal
        self.transient(parent)
        self.grab_set()

        # Layout
        self._build_ui(initial_category)
        self._refresh_icons()

    def _build_ui(self, initial_category: str):
        # Top Header & Controls Frame
        header_frame = ctk.CTkFrame(self, corner_radius=0)
        header_frame.pack(fill="x", padx=16, pady=(14, 8))

        # Title & Action Buttons Row
        top_row = ctk.CTkFrame(header_frame, fg_color="transparent")
        top_row.pack(fill="x", pady=(0, 10))

        lbl_title = ctk.CTkLabel(
            top_row,
            text="Icon library",
            font=ctk.CTkFont(size=18, weight="bold"),
        )
        lbl_title.pack(side="left")

        btn_ai = ctk.CTkButton(
            top_row,
            text="Make an icon…",
            width=190,
            fg_color="#8B5CF6",
            hover_color="#7C3AED",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._launch_ai_generator,
        )
        btn_ai.pack(side="right", padx=(8, 0))

        btn_open_folder = ctk.CTkButton(
            top_row,
            text="Open my icons folder",
            width=150,
            fg_color="gray30",
            hover_color="gray40",
            font=ctk.CTkFont(size=12),
            command=self._open_custom_folder,
        )
        btn_open_folder.pack(side="right")

        # Search Bar Row
        search_row = ctk.CTkFrame(header_frame, fg_color="transparent")
        search_row.pack(fill="x", pady=(0, 8))

        # No textvariable: CTkEntry hides its placeholder when one is attached
        self.entry_search = ctk.CTkEntry(
            search_row,
            placeholder_text="Search icons, e.g. torx, fuse, bearing",
            height=34,
            font=ctk.CTkFont(size=13),
        )
        self.entry_search.pack(fill="x", expand=True)
        self.entry_search.bind("<KeyRelease>", lambda e: self._refresh_icons())

        # Category Tabs Row
        cat_row = ctk.CTkFrame(header_frame, fg_color="transparent")
        cat_row.pack(fill="x")

        self.category_var = tk.StringVar(value=initial_category)
        self.seg_category = ctk.CTkSegmentedButton(
            cat_row,
            values=icon_manager.CATEGORIES,
            variable=self.category_var,
            command=lambda c: self._refresh_icons(),
            height=32,
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        self.seg_category.pack(fill="x")

        # Main Scrollable Grid Area
        self.scroll_grid = ctk.CTkScrollableFrame(self, corner_radius=8)
        self.scroll_grid.pack(fill="both", expand=True, padx=16, pady=8)

        # Bottom Action Bar
        bottom_bar = ctk.CTkFrame(self, height=60, corner_radius=0)
        bottom_bar.pack(fill="x", side="bottom", padx=16, pady=(0, 14))

        # Selected preview badge
        self.preview_badge = ctk.CTkLabel(
            bottom_bar,
            text="No icon selected",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="gray70",
        )
        self.preview_badge.pack(side="left", padx=10)

        # Right buttons
        self.btn_use = ctk.CTkButton(
            bottom_bar,
            text="Insert icon",
            width=170,
            height=36,
            fg_color="#10B981",
            hover_color="#059669",
            font=ctk.CTkFont(size=13, weight="bold"),
            state="disabled",
            command=self._confirm_selection,
        )
        self.btn_use.pack(side="right", padx=(8, 0))

        btn_cancel = ctk.CTkButton(
            bottom_bar,
            text="Cancel",
            width=100,
            height=36,
            fg_color="gray30",
            hover_color="gray40",
            command=self.destroy,
        )
        btn_cancel.pack(side="right")

    def _open_custom_folder(self):
        user_dir = os.path.normpath(config_manager.user_icons_dir)
        os.makedirs(user_dir, exist_ok=True)
        try:
            if sys.platform == "win32":
                os.startfile(user_dir)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", user_dir])
            else:
                subprocess.Popen(["xdg-open", user_dir])
        except Exception:
            if sys.platform == "win32":
                try:
                    subprocess.Popen(["explorer", user_dir])
                except Exception:
                    pass

    def _launch_ai_generator(self):
        if self.on_open_ai_generator:
            self.on_open_ai_generator()
        else:
            from ui.ai_generator_dialog import AIGeneratorDialog
            def on_ai_saved(icon_path: str):
                icon_manager.reload()
                self._refresh_icons()
                self._select_icon_by_path(icon_path)

            AIGeneratorDialog(self, on_save_callback=on_ai_saved)

    def _get_thumbnail(self, file_path: str, size: int = 56) -> Optional[ctk.CTkImage]:
        if file_path in self._ctk_image_cache:
            return self._ctk_image_cache[file_path]

        try:
            pil_img = Image.open(file_path).convert("RGBA")
            # Downsample for thumbnail
            pil_img.thumbnail((size, size), Image.Resampling.LANCZOS)
            ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(size, size))
            self._ctk_image_cache[file_path] = ctk_img
            return ctk_img
        except Exception:
            return None

    def _refresh_icons(self):
        # 1. Immediately reset scroll position to top
        self._reset_scroll_top()

        # 2. Clear existing items
        for child in self.scroll_grid.winfo_children():
            child.destroy()

        category = self.category_var.get()
        query = self.entry_search.get()
        icons = icon_manager.list_icons(category=category, search_query=query)

        # Configure columns (5 columns)
        cols = 5
        for col_idx in range(cols):
            self.scroll_grid.grid_columnconfigure(col_idx, weight=1, uniform="col")

        if not icons:
            empty_lbl = ctk.CTkLabel(
                self.scroll_grid,
                text=f"No icons found matching '{query}' in {category}." if query else f"No icons in {category} yet.",
                font=ctk.CTkFont(size=14),
                text_color="gray60",
            )
            empty_lbl.grid(row=0, column=0, columnspan=cols, pady=40)
            return

        self._tiles = {}
        for idx, item in enumerate(icons):
            row = idx // cols
            col = idx % cols

            thumb = self._get_thumbnail(item.file_path, size=52)

            # Light tiles: icons print black on white tape, so show them that way
            tile = ctk.CTkButton(
                self.scroll_grid,
                text=f"\n{self._short_title(item.title)}",
                image=thumb,
                compound="top",
                width=135,
                height=110,
                corner_radius=8,
                fg_color=TILE_BG,
                hover_color=TILE_HOVER,
                text_color="#222222",
                border_width=2,
                border_color=TILE_BG,
                font=ctk.CTkFont(size=11),
                command=lambda it=item: self._select_icon(it),
            )
            tile.grid(row=row, column=col, padx=6, pady=6, sticky="nsew")
            tile.bind("<Double-Button-1>", lambda e, it=item: (self._select_icon(it), self._confirm_selection()))
            self._tiles[item.file_path] = tile
            if self.selected_icon and self.selected_icon.file_path == item.file_path:
                tile.configure(border_color=TILE_SELECTED)

        # Ensure scroll snaps to top after new widgets are rendered
        self.after(10, self._reset_scroll_top)

    def _reset_scroll_top(self):
        try:
            if hasattr(self.scroll_grid, "_parent_canvas"):
                self.scroll_grid._parent_canvas.yview_moveto(0.0)
        except Exception:
            pass

    @staticmethod
    def _short_title(title: str, limit: int = TITLE_MAX_CHARS) -> str:
        """Cuts long names at the end so the start of the name always shows."""
        return title if len(title) <= limit else title[: limit - 1].rstrip() + "…"

    def _select_icon(self, icon: IconItem):
        previous = self.selected_icon
        self.selected_icon = icon
        tiles = getattr(self, "_tiles", {})
        if previous and previous.file_path in tiles:
            tiles[previous.file_path].configure(border_color=TILE_BG)
        if icon.file_path in tiles:
            tiles[icon.file_path].configure(border_color=TILE_SELECTED)
        self.preview_badge.configure(
            text=f"Selected: {icon.title} ({icon.category})",
            text_color="#10B981",
        )
        self.btn_use.configure(state="normal")

    def _select_icon_by_path(self, path: str):
        for item in icon_manager.list_icons():
            if item.file_path == path:
                self._select_icon(item)
                break

    def _confirm_selection(self):
        if self.selected_icon:
            self.on_select_callback(self.selected_icon.file_path)
            self.destroy()
