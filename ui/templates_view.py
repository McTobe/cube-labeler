#!/usr/bin/env python3
"""
Templates view: the user's own saved templates, preset cards with preview pictures, and
opening template files.
"""

import os
import re
import sys
from typing import Callable, Dict, Optional, Tuple

import customtkinter as ctk
from PIL import Image

from ui.templates import BUILTIN_PRESETS, delete_user_template, list_user_templates, load_config_from_json
from ui.widgets import MUTED_TEXT

CARD_IMAGE_SIZE = (220, 70)
COLUMNS = 3
USER_CARD_IMAGE_SIZE = (150, 48)
USER_COLUMNS = 4

# Pictures of saved templates: (path, modified time) -> picture, or None when it can't be drawn
_user_previews: Dict[Tuple[str, float], Optional[Image.Image]] = {}


def _assets_dir() -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, "assets")


def user_template_preview(path: str) -> Optional[Image.Image]:
    """A picture of a saved template, drawn the way the label prints; drawn again only after it changes."""
    try:
        key = (path, os.path.getmtime(path))
    except OSError:
        return None
    if key not in _user_previews:
        try:
            from core.label_renderer import LabelRenderer

            img = LabelRenderer().render(load_config_from_json(path))[0].convert("RGB")
            img.thumbnail(USER_CARD_IMAGE_SIZE, Image.Resampling.LANCZOS)
        except Exception:
            img = None
        _user_previews[key] = img
    return _user_previews[key]


def preview_path_for(preset_key: str) -> str:
    """Preview files are named after the preset key, e.g. "Cable Flag / Wrap" -> cable_flag___wrap_preview.png."""
    slug = re.sub(r"[^a-z0-9]", "_", preset_key.lower())
    return os.path.join(_assets_dir(), f"{slug}_preview.png")


class TemplatesView(ctk.CTkFrame):
    def __init__(
        self,
        master,
        on_apply: Callable[[str], None],
        on_save: Callable[[], None],
        on_open: Callable[[], None],
        on_open_user: Optional[Callable[[str], None]] = None,
        templates_folder: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._images: Dict[str, Optional[ctk.CTkImage]] = {}
        self._on_open_user = on_open_user
        self._templates_folder = templates_folder

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=4, pady=(4, 10))
        ctk.CTkLabel(top, text="Templates", font=ctk.CTkFont(size=18, weight="bold")).pack(side="left")
        self.btn_load_template = ctk.CTkButton(
            top,
            text="Open file…",
            width=110,
            fg_color="transparent",
            border_width=1,
            text_color=("gray10", "gray90"),
            command=on_open,
        )
        self.btn_load_template.pack(side="right")
        self.btn_save_template = ctk.CTkButton(top, text="Save current label…", width=150, command=on_save)
        self.btn_save_template.pack(side="right", padx=8)

        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        # The user's own templates
        ctk.CTkLabel(scroll, text="My templates", font=ctk.CTkFont(size=14, weight="bold"), anchor="w").pack(
            fill="x", padx=4, pady=(0, 4)
        )
        self.user_list = ctk.CTkFrame(scroll, fg_color="transparent")
        self.user_list.pack(fill="x", padx=2, pady=(0, 14))
        self.refresh_user_templates()

        ctk.CTkLabel(scroll, text="Starting points", font=ctk.CTkFont(size=14, weight="bold"), anchor="w").pack(
            fill="x", padx=4
        )
        ctk.CTkLabel(
            scroll,
            text="Pick a starting point. It opens in the text label editor, where you can change anything.",
            anchor="w",
            text_color=MUTED_TEXT,
        ).pack(fill="x", padx=4, pady=(0, 8))

        grid = ctk.CTkFrame(scroll, fg_color="transparent")
        grid.pack(fill="both", expand=True)
        for col in range(COLUMNS):
            grid.grid_columnconfigure(col, weight=1, uniform="card")

        self.cards = {}
        for idx, (key, preset) in enumerate(BUILTIN_PRESETS.items()):
            card = self._make_card(grid, key, preset, on_apply)
            card.grid(row=idx // COLUMNS, column=idx % COLUMNS, padx=6, pady=6, sticky="nsew")
            self.cards[key] = card

    def refresh_user_templates(self):
        """Lists the saved templates again, e.g. after saving one or restoring a backup."""
        for child in self.user_list.winfo_children():
            child.destroy()
        templates = list_user_templates(self._templates_folder)
        self.user_rows = {}
        if not templates:
            ctk.CTkLabel(
                self.user_list,
                text="Labels you save with “Save current label…” show up here, and are included in backups.",
                anchor="w",
                text_color=MUTED_TEXT,
            ).pack(fill="x", padx=2)
            return
        for col in range(USER_COLUMNS):
            self.user_list.grid_columnconfigure(col, weight=1, uniform="user_card")
        for idx, (name, path) in enumerate(templates):
            card = self._make_user_card(name, path)
            card.grid(row=idx // USER_COLUMNS, column=idx % USER_COLUMNS, padx=5, pady=5, sticky="nsew")
            self.user_rows[name] = card

    def _make_user_card(self, name: str, path: str):
        card = ctk.CTkFrame(self.user_list, corner_radius=10)
        # Like the starting points, clicking the picture opens the template
        img = user_template_preview(path)
        image = ctk.CTkImage(light_image=img, dark_image=img, size=img.size) if img else None
        self._images[path] = image
        open_template = lambda p=path: self._on_open_user and self._on_open_user(p)

        ctk.CTkButton(
            card,
            text="" if image else "No preview",
            image=image,
            height=64,
            fg_color=("gray85", "gray20"),
            hover_color=("gray78", "gray28"),
            text_color=MUTED_TEXT,
            command=open_template,
        ).pack(fill="x", padx=6, pady=(6, 4))
        footer = ctk.CTkFrame(card, fg_color="transparent")
        footer.pack(fill="x", padx=6, pady=(0, 6))
        ctk.CTkButton(
            footer, text="Delete", width=54, height=24, fg_color="gray30", hover_color="#B91C1C",
            font=ctk.CTkFont(size=11), command=lambda n=name, p=path: self._delete(n, p),
        ).pack(side="right")
        short = name if len(name) <= 22 else name[:21].rstrip() + "…"
        ctk.CTkLabel(footer, text=short, anchor="w", font=ctk.CTkFont(size=12, weight="bold")).pack(
            side="left", fill="x", expand=True, padx=(4, 4)
        )
        return card

    def _delete(self, name: str, path: str):
        from tkinter import messagebox

        if messagebox.askyesno("Delete template", f"Delete the template “{name}”?", parent=self):
            delete_user_template(path)
            self.refresh_user_templates()

    def _load_image(self, key: str) -> Optional[ctk.CTkImage]:
        path = preview_path_for(key)
        if not os.path.isfile(path):
            return None
        try:
            img = Image.open(path).convert("RGB")
            img.thumbnail(CARD_IMAGE_SIZE, Image.Resampling.LANCZOS)
            return ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
        except Exception:
            return None

    def _make_card(self, parent, key: str, preset: dict, on_apply: Callable[[str], None]):
        card = ctk.CTkFrame(parent, corner_radius=10)
        image = self._load_image(key)
        self._images[key] = image

        picture = ctk.CTkButton(
            card,
            text="" if image else preset.get("name", key),
            image=image,
            height=90,
            fg_color=("gray85", "gray20"),
            hover_color=("gray78", "gray28"),
            text_color=("gray10", "gray90"),
            command=lambda k=key: on_apply(k),
        )
        picture.pack(fill="x", padx=8, pady=(8, 6))

        ctk.CTkLabel(card, text=preset.get("name", key), font=ctk.CTkFont(size=13, weight="bold"), anchor="w").pack(
            fill="x", padx=10
        )
        ctk.CTkLabel(
            card,
            text=preset.get("description", ""),
            anchor="w",
            justify="left",
            wraplength=220,
            text_color=MUTED_TEXT,
            font=ctk.CTkFont(size=11),
        ).pack(fill="x", padx=10, pady=(0, 10))
        return card
