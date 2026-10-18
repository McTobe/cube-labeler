#!/usr/bin/env python3
"""
Settings view: label language, Gemini API key and simulation mode.
"""

import webbrowser
from typing import Callable

import customtkinter as ctk

from core.config import config_manager
from core.label_language import LANGUAGES, get_label_language
from ui.widgets import MUTED_TEXT

API_KEY_URL = "https://aistudio.google.com/app/apikey"


class SettingsView(ctk.CTkFrame):
    def __init__(
        self,
        master,
        virtual_var: ctk.BooleanVar,
        on_virtual_toggle: Callable[[], None],
        on_language_changed: Callable[[str], None],
        on_status: Callable[[str], None],
        **kwargs,
    ):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._on_language_changed = on_language_changed
        self._on_status = on_status

        ctk.CTkLabel(self, text="Settings", font=ctk.CTkFont(size=18, weight="bold"), anchor="w").pack(
            fill="x", padx=4, pady=(4, 12)
        )

        # Label language
        lang_card = self._card("Bin label language")
        ctk.CTkLabel(
            lang_card,
            text="Language for the suggested names on bin labels, like Screws or Bearings. "
                 "Names you have already typed are not changed.",
            anchor="w",
            justify="left",
            wraplength=560,
            text_color=MUTED_TEXT,
        ).pack(fill="x", pady=(0, 6))
        self.language_combo = ctk.CTkComboBox(
            lang_card, values=list(LANGUAGES.values()), width=160, command=self._language_selected
        )
        self.language_combo.set(LANGUAGES[get_label_language()])
        self.language_combo.pack(anchor="w")

        # Gemini API key
        key_card = self._card("Gemini API key")
        ctk.CTkLabel(
            key_card,
            text="Needed only to make icons from photos or descriptions with Google Gemini. "
                 "Image generation needs billing enabled on your Google AI Studio project. "
                 "The key is stored encrypted for your Windows user.",
            anchor="w",
            justify="left",
            wraplength=560,
            text_color=MUTED_TEXT,
        ).pack(fill="x", pady=(0, 6))
        key_row = ctk.CTkFrame(key_card, fg_color="transparent")
        key_row.pack(fill="x")
        self.entry_api_key = ctk.CTkEntry(key_row, show="•", width=360, placeholder_text="Paste your API key")
        if config_manager.gemini_api_key:
            self.entry_api_key.insert(0, config_manager.gemini_api_key)
        self.entry_api_key.pack(side="left")
        ctk.CTkButton(key_row, text="Save key", width=90, command=self._save_key).pack(side="left", padx=8)
        ctk.CTkButton(
            key_row,
            text="Get a key ↗",
            width=100,
            fg_color="transparent",
            border_width=1,
            text_color=("gray10", "gray90"),
            command=lambda: webbrowser.open(API_KEY_URL),
        ).pack(side="left")

        # Simulation
        sim_card = self._card("Simulation")
        ctk.CTkLabel(
            sim_card,
            text="Try the app without a printer. Printing is simulated and nothing is sent over Bluetooth.",
            anchor="w",
            justify="left",
            wraplength=560,
            text_color=MUTED_TEXT,
        ).pack(fill="x", pady=(0, 6))
        self.virtual_switch = ctk.CTkSwitch(
            sim_card, text="Simulate the printer", variable=virtual_var, command=on_virtual_toggle
        )
        self.virtual_switch.pack(anchor="w")

    def _card(self, title: str) -> ctk.CTkFrame:
        card = ctk.CTkFrame(self, corner_radius=10)
        card.pack(fill="x", padx=4, pady=(0, 10))
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=14, pady=12)
        ctk.CTkLabel(inner, text=title, font=ctk.CTkFont(size=14, weight="bold"), anchor="w").pack(fill="x")
        return inner

    def _language_selected(self, display_name: str):
        code = next((c for c, name in LANGUAGES.items() if name == display_name), None)
        if code:
            self._on_language_changed(code)

    def _save_key(self):
        from core.ai_generator import ai_generator

        key = self.entry_api_key.get().strip()
        config_manager.gemini_api_key = key
        ai_generator.api_key = key
        self._on_status("API key saved" if key else "API key removed")
