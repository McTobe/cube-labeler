#!/usr/bin/env python3
"""
Small reusable widgets for the main window: collapsible sections, labelled sliders
and the left navigation rail.
"""

from typing import Callable, Dict, List, Optional, Tuple

import customtkinter as ctk

ACCENT = "#1F6AA5"
ACCENT_HOVER = "#144870"
MUTED_TEXT = ("gray40", "gray60")


class Section(ctk.CTkFrame):
    """A titled block whose body can be collapsed by clicking the title."""

    def __init__(self, master, title: str, expanded: bool = True, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._title = title
        self._expanded = expanded

        self.header = ctk.CTkButton(
            self,
            text="",
            anchor="w",
            height=28,
            fg_color="transparent",
            hover_color=("gray85", "gray25"),
            text_color=("gray10", "gray90"),
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self.toggle,
        )
        self.header.pack(fill="x")

        self.body = ctk.CTkFrame(self, fg_color="transparent")
        if expanded:
            self.body.pack(fill="x", padx=(8, 0), pady=(2, 8))
        self._update_header()

    def _update_header(self):
        arrow = "▾" if self._expanded else "▸"
        self.header.configure(text=f"{arrow}  {self._title}")

    @property
    def expanded(self) -> bool:
        return self._expanded

    def set_expanded(self, expanded: bool):
        if expanded == self._expanded:
            return
        self._expanded = expanded
        if expanded:
            self.body.pack(fill="x", padx=(8, 0), pady=(2, 8))
        else:
            self.body.pack_forget()
        self._update_header()

    def toggle(self):
        self.set_expanded(not self._expanded)


def labeled_slider(
    parent,
    label: str,
    from_: float,
    to: float,
    steps: int,
    initial: float,
    value_text: str,
    command: Callable[[float], None],
) -> Tuple[ctk.CTkSlider, ctk.CTkLabel]:
    """A label and current value on one line with a full-width slider below."""
    row = ctk.CTkFrame(parent, fg_color="transparent")
    row.pack(fill="x", pady=(4, 0))
    ctk.CTkLabel(row, text=label, anchor="w").pack(side="left")
    value_label = ctk.CTkLabel(row, text=value_text, anchor="e", text_color=MUTED_TEXT)
    value_label.pack(side="right")

    slider = ctk.CTkSlider(parent, from_=from_, to=to, number_of_steps=steps, command=command)
    slider.set(initial)
    slider.pack(fill="x", pady=(0, 4))
    return slider, value_label


def field_label(parent, text: str):
    ctk.CTkLabel(parent, text=text, anchor="w").pack(fill="x", pady=(6, 2))


class Sidebar(ctk.CTkFrame):
    """Left navigation rail. Items are (key, title); the active item is highlighted."""

    def __init__(
        self,
        master,
        items: List[Tuple[str, str]],
        bottom_items: List[Tuple[str, str]],
        on_select: Callable[[str], None],
        **kwargs,
    ):
        super().__init__(master, width=170, corner_radius=10, **kwargs)
        self.pack_propagate(False)
        self.grid_propagate(False)
        self._on_select = on_select
        self._titles: Dict[str, str] = {}
        self.buttons: Dict[str, ctk.CTkButton] = {}
        self._active: Optional[str] = None

        for key, title in items:
            self._add_item(key, title, side="top")
        spacer = ctk.CTkFrame(self, fg_color="transparent")
        spacer.pack(fill="both", expand=True)
        for key, title in bottom_items:
            self._add_item(key, title, side="bottom")

    def _add_item(self, key: str, title: str, side: str):
        self._titles[key] = title
        btn = ctk.CTkButton(
            self,
            text=title,
            anchor="w",
            height=36,
            corner_radius=8,
            fg_color="transparent",
            hover_color=("gray80", "gray25"),
            text_color=("gray10", "gray90"),
            font=ctk.CTkFont(size=13),
            command=lambda k=key: self._on_select(k),
        )
        btn.pack(fill="x", padx=8, pady=(8 if side == "top" and not self.buttons else 2, 2), side=side)
        self.buttons[key] = btn

    @property
    def active(self) -> Optional[str]:
        return self._active

    def set_active(self, key: str):
        self._active = key
        for k, btn in self.buttons.items():
            if k == key:
                btn.configure(fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color="white")
            else:
                btn.configure(fg_color="transparent", hover_color=("gray80", "gray25"), text_color=("gray10", "gray90"))

    def set_badge(self, key: str, count: int):
        """Shows a count after an item's title, e.g. "Queue  3"."""
        title = self._titles[key]
        self.buttons[key].configure(text=f"{title}   {count}" if count else title)
