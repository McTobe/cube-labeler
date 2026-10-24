#!/usr/bin/env python3
"""
Interactive Icon Browser Dialog for Cube Labeler.
Category sidebar, search, thumbnail grid and a details panel with a print preview,
favourites, importing pictures and managing the user's own icons.
"""

import os
import sys
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Callable, Optional, Dict
import customtkinter as ctk
from PIL import Image

from core.icon_manager import (
    ALL, FAVOURITES, RECENT, USER_CATEGORY,
    icon_manager, IconItem, parse_keywords, print_preview,
)
from core.config import config_manager
# Imported here so automatic backups follow every change made in the library
from core.icon_backup import auto_backup  # noqa: F401

TILE_BG = "#F5F5F5"
TILE_HOVER = "#E3E3E3"
TILE_SELECTED = "#1F6AA5"
TITLE_MAX_CHARS = 20
TILE_W = 122
TILE_H = 104
SEARCH_DELAY_MS = 180
PREVIEW_SIZE = 112


class IconBrowserDialog(ctk.CTkToplevel):
    """Modal dialog allowing users to browse, search, and select icons."""

    def __init__(
        self,
        parent,
        on_select: Callable[[str], None],
        initial_category: str = ALL,
        title_suffix: str = "",
    ):
        super().__init__(parent)
        self.on_select_callback = on_select
        self.selected_icon: Optional[IconItem] = None
        self._ctk_image_cache: Dict[str, ctk.CTkImage] = {}
        self._tiles: Dict[str, ctk.CTkButton] = {}
        self._shown: list = []
        self._columns = 0
        self._search_job = None
        self._layout_job = None

        dialog_title = "Icon Library"
        if title_suffix:
            dialog_title += f" - {title_suffix}"
        self.title(dialog_title)
        self.geometry("1040x680")
        self.minsize(860, 520)

        # Make modal
        self.transient(parent)
        self.grab_set()

        if initial_category not in icon_manager.views:
            initial_category = ALL
        self.category_var = tk.StringVar(value=initial_category)

        self._build_ui()
        self._refresh_sidebar()
        self._refresh_icons()
        self._show_details(None)

    # ----- Layout -----

    def _build_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # Title and actions
        top_row = ctk.CTkFrame(self, fg_color="transparent")
        top_row.grid(row=0, column=0, columnspan=3, sticky="ew", padx=16, pady=(14, 6))
        ctk.CTkLabel(top_row, text="Icon library", font=ctk.CTkFont(size=18, weight="bold")).pack(side="left")

        ctk.CTkButton(
            top_row, text="Make an icon…", width=130, fg_color="#8B5CF6", hover_color="#7C3AED",
            font=ctk.CTkFont(size=12, weight="bold"), command=self._make_icon,
        ).pack(side="right", padx=(8, 0))
        ctk.CTkButton(
            top_row, text="Import image…", width=120, font=ctk.CTkFont(size=12),
            command=self._import_image,
        ).pack(side="right", padx=(8, 0))
        ctk.CTkButton(
            top_row, text="Backups…", width=100, fg_color="gray30", hover_color="gray40",
            font=ctk.CTkFont(size=12), command=self._open_backups,
        ).pack(side="right", padx=(8, 0))
        ctk.CTkButton(
            top_row, text="Open my icons folder", width=150, fg_color="gray30", hover_color="gray40",
            font=ctk.CTkFont(size=12), command=self._open_custom_folder,
        ).pack(side="right")

        # No textvariable: CTkEntry hides its placeholder when one is attached
        self.entry_search = ctk.CTkEntry(
            self, placeholder_text="Search icons, e.g. torx, wago, bearing, säkring",
            height=34, font=ctk.CTkFont(size=13),
        )
        self.entry_search.grid(row=1, column=0, columnspan=3, sticky="ew", padx=16, pady=(0, 8))
        self.entry_search.bind("<KeyRelease>", self._on_search_typed)
        self.entry_search.bind("<Escape>", lambda e: self._clear_search())

        # Category sidebar
        self.sidebar = ctk.CTkScrollableFrame(self, width=190, corner_radius=8)
        self.sidebar.grid(row=2, column=0, sticky="nsw", padx=(16, 8), pady=0)
        self._sidebar_buttons: Dict[str, ctk.CTkButton] = {}

        # Icon grid
        self.scroll_grid = ctk.CTkScrollableFrame(self, corner_radius=8)
        self.scroll_grid.grid(row=2, column=1, sticky="nsew", pady=0)
        self.scroll_grid._parent_canvas.bind("<Configure>", self._on_grid_resized, add="+")
        self.empty_label = ctk.CTkLabel(self.scroll_grid, text="", font=ctk.CTkFont(size=14), text_color="gray60")

        # Details panel
        self.details = ctk.CTkFrame(self, width=260, corner_radius=8)
        self.details.grid(row=2, column=2, sticky="nse", padx=(8, 16), pady=0)
        self.details.grid_propagate(False)
        self._build_details()

        # Bottom bar
        bottom_bar = ctk.CTkFrame(self, fg_color="transparent")
        bottom_bar.grid(row=3, column=0, columnspan=3, sticky="ew", padx=16, pady=(8, 14))
        self.preview_badge = ctk.CTkLabel(
            bottom_bar, text="No icon selected", font=ctk.CTkFont(size=13, weight="bold"), text_color="gray70",
        )
        self.preview_badge.pack(side="left", padx=4)
        self.btn_use = ctk.CTkButton(
            bottom_bar, text="Insert icon", width=170, height=36, fg_color="#10B981", hover_color="#059669",
            font=ctk.CTkFont(size=13, weight="bold"), state="disabled", command=self._confirm_selection,
        )
        self.btn_use.pack(side="right", padx=(8, 0))
        ctk.CTkButton(
            bottom_bar, text="Cancel", width=100, height=36, fg_color="gray30", hover_color="gray40",
            command=self.destroy,
        ).pack(side="right")

    def _build_details(self):
        d = self.details
        previews = ctk.CTkFrame(d, fg_color="transparent")
        previews.pack(fill="x", padx=10, pady=(12, 0))
        self.lbl_big = ctk.CTkLabel(previews, text="", width=PREVIEW_SIZE, height=PREVIEW_SIZE, fg_color=TILE_BG, corner_radius=8)
        self.lbl_big.grid(row=0, column=0, padx=(0, 6))
        self.lbl_print = ctk.CTkLabel(previews, text="", width=PREVIEW_SIZE, height=PREVIEW_SIZE, fg_color="white", corner_radius=8)
        self.lbl_print.grid(row=0, column=1)
        ctk.CTkLabel(previews, text="Picture", font=ctk.CTkFont(size=11), text_color="gray60").grid(row=1, column=0)
        self.lbl_print_caption = ctk.CTkLabel(previews, text="How it prints", font=ctk.CTkFont(size=11), text_color="gray60")
        self.lbl_print_caption.grid(row=1, column=1)

        self.lbl_name = ctk.CTkLabel(d, text="", font=ctk.CTkFont(size=13, weight="bold"), wraplength=220, justify="left")
        self.lbl_name.pack(anchor="w", padx=12)
        self.lbl_meta = ctk.CTkLabel(d, text="", font=ctk.CTkFont(size=11), text_color="gray60", wraplength=220, justify="left")
        self.lbl_meta.pack(anchor="w", padx=12, pady=(0, 6))

        self.btn_fav = ctk.CTkButton(d, text="☆ Add to favourites", height=28, fg_color="gray30", hover_color="gray40",
                                     command=self._toggle_favourite)
        self.btn_fav.pack(fill="x", padx=12, pady=(0, 6))
        # "Edit icon…" for the user's own icons, "Edit a copy…" for built-in ones
        self.btn_edit = ctk.CTkButton(d, text="Edit icon…", height=28, command=self._edit_selected)
        self.btn_edit.pack(fill="x", padx=12, pady=(0, 6))

        # Only for the user's own icons
        self.user_box = ctk.CTkFrame(d, fg_color="transparent")
        self.entry_title = ctk.CTkEntry(self.user_box, placeholder_text="Name", height=28)
        self.entry_title.pack(fill="x", pady=(0, 4))
        self.cat_menu = ctk.CTkOptionMenu(self.user_box, values=[USER_CATEGORY] + icon_manager.built_in_categories, height=28)
        self.cat_menu.pack(fill="x", pady=(0, 4))
        self.entry_keywords = ctk.CTkEntry(self.user_box, placeholder_text="Search words, comma separated", height=28)
        self.entry_keywords.pack(fill="x", pady=(0, 4))
        row = ctk.CTkFrame(self.user_box, fg_color="transparent")
        row.pack(fill="x")
        ctk.CTkButton(row, text="Save", width=90, height=28, command=self._save_user_details).pack(side="left")
        ctk.CTkButton(row, text="Delete", width=90, height=28, fg_color="#B91C1C", hover_color="#991B1B",
                      command=self._delete_user_icon).pack(side="right")

    # ----- Sidebar -----

    def _refresh_sidebar(self):
        counts = icon_manager.category_counts()
        for view in icon_manager.views:
            label = f"{view}  ({counts.get(view, 0)})"
            btn = self._sidebar_buttons.get(view)
            if btn is None:
                btn = ctk.CTkButton(
                    self.sidebar, text=label, anchor="w", height=30, corner_radius=6,
                    font=ctk.CTkFont(size=12), command=lambda v=view: self._select_category(v),
                )
                btn.pack(fill="x", pady=1)
                if view in (RECENT, USER_CATEGORY):
                    # A little space between the special views and the categories
                    ctk.CTkFrame(self.sidebar, height=6, fg_color="transparent").pack(fill="x")
                self._sidebar_buttons[view] = btn
            else:
                btn.configure(text=label)
            active = view == self.category_var.get()
            btn.configure(
                fg_color=TILE_SELECTED if active else "transparent",
                text_color=("white" if active else ("gray10", "gray90")),
                hover_color=("gray80", "gray30"),
            )

    def _select_category(self, view: str):
        self.category_var.set(view)
        self._refresh_sidebar()
        self._refresh_icons()

    # ----- Grid -----

    def _on_search_typed(self, _event=None):
        if self._search_job:
            self.after_cancel(self._search_job)
        self._search_job = self.after(SEARCH_DELAY_MS, self._refresh_icons)

    def _clear_search(self):
        self.entry_search.delete(0, "end")
        self._refresh_icons()

    def _on_grid_resized(self, _event=None):
        if self._layout_job:
            self.after_cancel(self._layout_job)
        self._layout_job = self.after(60, self._layout_tiles)

    def _get_thumbnail(self, file_path: str, size: int = 56) -> Optional[ctk.CTkImage]:
        key = f"{file_path}@{size}"
        if key in self._ctk_image_cache:
            return self._ctk_image_cache[key]
        try:
            with Image.open(file_path) as src:
                pil_img = src.convert("RGBA")
            pil_img.thumbnail((size, size), Image.Resampling.LANCZOS)
            ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=pil_img.size)
            self._ctk_image_cache[key] = ctk_img
            return ctk_img
        except Exception:
            return None

    def _tile_for(self, item: IconItem) -> ctk.CTkButton:
        """Tiles are made once and reused, so filtering and searching stay quick."""
        tile = self._tiles.get(item.file_path)
        text = f"\n{self._short_title(item.title)}"
        if tile is None:
            # Light tiles: icons print black on white tape, so show them that way
            tile = ctk.CTkButton(
                self.scroll_grid, text=text, image=self._get_thumbnail(item.file_path, 52), compound="top",
                width=TILE_W, height=TILE_H, corner_radius=8, fg_color=TILE_BG, hover_color=TILE_HOVER,
                text_color="#222222", border_width=2, border_color=TILE_BG, font=ctk.CTkFont(size=11),
                command=lambda p=item.file_path: self._select_path(p),
            )
            tile.bind("<Double-Button-1>", lambda e, p=item.file_path: (self._select_path(p), self._confirm_selection()))
            self._tiles[item.file_path] = tile
        else:
            tile.configure(text=text)
        selected = self.selected_icon is not None and self.selected_icon.file_path == item.file_path
        tile.configure(border_color=TILE_SELECTED if selected else TILE_BG)
        return tile

    def _refresh_icons(self):
        self._search_job = None
        category = self.category_var.get()
        query = self.entry_search.get()
        self._shown = icon_manager.list_icons(category=category, search_query=query)
        self._columns = 0  # force a new layout
        self._layout_tiles()
        self._reset_scroll_top()

    def _layout_tiles(self):
        self._layout_job = None
        width = self.scroll_grid._parent_canvas.winfo_width()
        cols = max(1, (width - 16) // (TILE_W + 12)) if width > 1 else 4
        if cols == self._columns:
            return
        self._columns = cols

        for child in self.scroll_grid.grid_slaves():
            child.grid_forget()
        for col_idx in range(12):
            self.scroll_grid.grid_columnconfigure(col_idx, weight=1 if col_idx < cols else 0, uniform="col" if col_idx < cols else "")

        if not self._shown:
            query = self.entry_search.get().strip()
            category = self.category_var.get()
            if query:
                text = f"No icons match “{query}” in {category}."
            elif category == FAVOURITES:
                text = "No favourites yet. Pick an icon and press ☆ to add it."
            elif category == RECENT:
                text = "Icons you insert show up here."
            else:
                text = f"No icons in {category} yet."
            self.empty_label.configure(text=text)
            self.empty_label.grid(row=0, column=0, columnspan=cols, pady=40)
            return

        for idx, item in enumerate(self._shown):
            self._tile_for(item).grid(row=idx // cols, column=idx % cols, padx=6, pady=6, sticky="nsew")

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

    # ----- Selection and details -----

    def _select_path(self, path: str):
        item = icon_manager.get_icon_by_path(path)
        if item:
            self._select_icon(item)

    def _select_icon(self, icon: IconItem):
        previous = self.selected_icon
        self.selected_icon = icon
        if previous and previous.file_path in self._tiles:
            self._tiles[previous.file_path].configure(border_color=TILE_BG)
        if icon.file_path in self._tiles:
            self._tiles[icon.file_path].configure(border_color=TILE_SELECTED)
        self.preview_badge.configure(text=f"Selected: {icon.title}", text_color="#10B981")
        self.btn_use.configure(state="normal")
        self._show_details(icon)

    def _select_icon_by_path(self, path: str):
        self._select_path(path)

    def _show_details(self, icon: Optional[IconItem]):
        if icon is None:
            self.lbl_big.configure(image=None, text="Pick an icon")
            self.lbl_print.configure(image=None, text="")
            self.lbl_name.configure(text="")
            self.lbl_meta.configure(text="")
            self.btn_fav.pack_forget()
            self.btn_edit.pack_forget()
            self.user_box.pack_forget()
            return

        big = self._get_thumbnail(icon.file_path, PREVIEW_SIZE - 12)
        self.lbl_big.configure(image=big, text="")
        dots = print_preview(icon.file_path)
        if dots is not None:
            dots = dots.convert("RGB").resize((dots.width * 2, dots.height * 2), Image.Resampling.NEAREST)
            dots_img = ctk.CTkImage(light_image=dots, dark_image=dots, size=dots.size)
            self.lbl_print.configure(image=dots_img, text="")
            self._print_image = dots_img  # keep a reference
        else:
            self.lbl_print.configure(image=None, text="Can't read this picture")

        self.lbl_name.configure(text=icon.title)
        where = "Your icon" + (f" · {icon.category}" if icon.category != USER_CATEGORY else "") if icon.user else icon.category
        words = ", ".join(icon.keywords[:8])
        self.lbl_meta.configure(text=f"{where}\n{words}" if words else where)

        self.btn_fav.pack(fill="x", padx=12, pady=(0, 6))
        self._update_fav_button(icon)
        self.btn_edit.configure(text="Edit icon…" if icon.user else "Edit a copy…")
        self.btn_edit.pack(fill="x", padx=12, pady=(0, 6))

        if icon.user:
            self.entry_title.delete(0, "end")
            self.entry_title.insert(0, icon.title)
            self.cat_menu.set(icon.category)
            self.entry_keywords.delete(0, "end")
            self.entry_keywords.insert(0, ", ".join(icon.keywords))
            self.user_box.pack(fill="x", padx=12, pady=(4, 12))
        else:
            self.user_box.pack_forget()

    def _update_fav_button(self, icon: IconItem):
        fav = icon_manager.is_favourite(icon)
        self.btn_fav.configure(text="★ Favourite" if fav else "☆ Add to favourites",
                               fg_color="#D97706" if fav else "gray30", hover_color="#B45309" if fav else "gray40")

    def _toggle_favourite(self):
        if not self.selected_icon:
            return
        icon_manager.toggle_favourite(self.selected_icon)
        self._update_fav_button(self.selected_icon)
        self._refresh_sidebar()
        if self.category_var.get() == FAVOURITES:
            self._refresh_icons()

    def _after_library_change(self, select_path: Optional[str] = None):
        """Refreshes everything after the user's icons changed on disk."""
        self.selected_icon = None
        for tile in self._tiles.values():
            tile.destroy()
        self._tiles.clear()
        self._ctk_image_cache.clear()
        self._refresh_sidebar()
        self._refresh_icons()
        if select_path:
            self._select_path(select_path)
        if not self.selected_icon:
            self.preview_badge.configure(text="No icon selected", text_color="gray70")
            self.btn_use.configure(state="disabled")
            self._show_details(None)

    def _save_user_details(self):
        icon = self.selected_icon
        if not icon or not icon.user:
            return
        updated = icon_manager.update_user_icon(
            icon, self.entry_title.get(), self.cat_menu.get(), parse_keywords(self.entry_keywords.get()),
        )
        self._after_library_change(updated.file_path if updated else None)

    def _delete_user_icon(self):
        icon = self.selected_icon
        if not icon or not icon.user:
            return
        if not messagebox.askyesno("Delete icon", f"Delete “{icon.title}” from your icons?", parent=self):
            return
        if not icon_manager.delete_user_icon(icon):
            messagebox.showerror("Delete icon", "The icon file could not be deleted.", parent=self)
        self._after_library_change()

    # ----- Adding icons -----

    def _import_image(self):
        path = filedialog.askopenfilename(
            parent=self, title="Import an image as an icon",
            filetypes=[("Images", "*.png;*.jpg;*.jpeg;*.bmp;*.webp;*.gif"), ("All files", "*.*")],
        )
        if path:
            self._open_editor(picture_path=path)

    def _make_icon(self):
        self._open_editor()

    def _edit_selected(self):
        if self.selected_icon:
            self._open_editor(icon=self.selected_icon)

    def _open_editor(self, picture_path: Optional[str] = None, icon: Optional[IconItem] = None):
        """Opens the icon editor; new icons go in the category shown, when it is a real one."""
        from ui.icon_editor_dialog import IconEditorDialog

        category = self.category_var.get()
        if category not in icon_manager.built_in_categories:
            category = USER_CATEGORY
        editor = IconEditorDialog(self, on_saved=self._on_icon_saved, picture_path=picture_path,
                                  category=category, icon=icon)
        # The editor takes the input grab while it is open; take it back afterwards
        editor.bind("<Destroy>", lambda e: e.widget is editor and self.after(10, self._take_grab), add="+")
        return editor

    def _open_backups(self):
        from ui.backup_dialog import BackupDialog

        dialog = BackupDialog(self, on_changed=self._after_library_change)
        dialog.bind("<Destroy>", lambda e: e.widget is dialog and self.after(10, self._take_grab), add="+")
        return dialog

    def _take_grab(self):
        try:
            if self.winfo_exists():
                self.grab_set()
                self.focus_force()
        except tk.TclError:
            pass

    def _on_icon_saved(self, path: str, insert: bool):
        self._after_library_change(path)
        if insert and self.selected_icon:
            self._confirm_selection()

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

    def _confirm_selection(self):
        if self.selected_icon:
            icon_manager.mark_used(self.selected_icon)
            self.on_select_callback(self.selected_icon.file_path)
            self.destroy()
