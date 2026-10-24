#!/usr/bin/env python3
"""
Settings view: label language, AI service and API key, backups and simulation mode.
"""

import webbrowser
from typing import Callable

import customtkinter as ctk

from core.ai_generator import PROVIDERS, current_provider, provider_by_name
from core.config import config_manager
from core.label_language import LANGUAGES, get_label_language
from ui.widgets import MUTED_TEXT



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

        # AI service for redrawing pictures as icons
        ai_card = self._card("AI icons")
        ctk.CTkLabel(
            ai_card,
            text="Optional. The icon editor can send one of your pictures to an AI service to redraw it as an icon. "
                 "Pick the service and paste your own API key; keys are stored encrypted for your Windows user.",
            anchor="w",
            justify="left",
            wraplength=560,
            text_color=MUTED_TEXT,
        ).pack(fill="x", pady=(0, 6))
        self.provider_menu = ctk.CTkSegmentedButton(
            ai_card, values=[p.name for p in PROVIDERS.values()], command=self._provider_selected
        )
        self.provider_menu.pack(anchor="w", pady=(0, 6))
        self.lbl_provider_note = ctk.CTkLabel(
            ai_card, text="", anchor="w", justify="left", wraplength=560, text_color=MUTED_TEXT,
            font=ctk.CTkFont(size=11),
        )
        self.lbl_provider_note.pack(fill="x", pady=(0, 6))
        key_row = ctk.CTkFrame(ai_card, fg_color="transparent")
        key_row.pack(fill="x")
        self.entry_api_key = ctk.CTkEntry(key_row, show="•", width=360, placeholder_text="Paste your API key")
        self.entry_api_key.pack(side="left")
        ctk.CTkButton(key_row, text="Save", width=90, command=self._save_key).pack(side="left", padx=8)
        ctk.CTkButton(
            key_row,
            text="Get a key ↗",
            width=100,
            fg_color="transparent",
            border_width=1,
            text_color=("gray10", "gray90"),
            command=lambda: webbrowser.open(self._provider().key_url),
        ).pack(side="left")
        model_row = ctk.CTkFrame(ai_card, fg_color="transparent")
        model_row.pack(fill="x", pady=(6, 0))
        ctk.CTkLabel(model_row, text="Model", width=50, anchor="w").pack(side="left")
        self.entry_model = ctk.CTkEntry(model_row, width=310)
        self.entry_model.pack(side="left")
        ctk.CTkLabel(model_row, text="Leave empty for the default", text_color=MUTED_TEXT,
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=8)
        self.provider_menu.set(current_provider().name)
        self._show_provider()

        # Backups
        backup_card = self._card("Backups")
        ctk.CTkLabel(
            backup_card,
            text="Back up your icons, saved templates and settings to a file, or automatically to a "
                 "Google Drive, OneDrive or Dropbox folder.",
            anchor="w",
            justify="left",
            wraplength=560,
            text_color=MUTED_TEXT,
        ).pack(fill="x", pady=(0, 6))
        backup_row = ctk.CTkFrame(backup_card, fg_color="transparent")
        backup_row.pack(fill="x")
        ctk.CTkButton(backup_row, text="Backups…", width=110, command=self._open_backups).pack(side="left")
        self.lbl_backup = ctk.CTkLabel(backup_row, text="", anchor="w", font=ctk.CTkFont(size=12))
        self.lbl_backup.pack(side="left", padx=12)
        self.refresh_backup_status()

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

    def refresh_backup_status(self):
        from ui.backup_dialog import backup_status

        text, colour, _on = backup_status()
        self.lbl_backup.configure(text=text, text_color=colour)

    def _open_backups(self):
        from ui.backup_dialog import BackupDialog

        dialog = BackupDialog(self.winfo_toplevel(), on_changed=lambda: None)
        dialog.bind("<Destroy>", lambda e: e.widget is dialog and self.after(10, self.refresh_backup_status), add="+")

    def _provider(self):
        return provider_by_name(self.provider_menu.get()) or current_provider()

    def _show_provider(self):
        provider = self._provider()
        self.lbl_provider_note.configure(text=provider.key_note)
        self.entry_api_key.delete(0, "end")
        key = config_manager.api_key(provider.id)
        if key:
            self.entry_api_key.insert(0, key)
        self.entry_model.delete(0, "end")
        model = config_manager.ai_model(provider.id)
        if model:
            self.entry_model.insert(0, model)
        self.entry_model.configure(placeholder_text=provider.default_model)

    def _provider_selected(self, name: str):
        provider = provider_by_name(name)
        if provider:
            config_manager.ai_provider = provider.id
            self._show_provider()
            self._on_status(f"AI icons now use {provider.name}")

    def _save_key(self):
        provider = self._provider()
        key = self.entry_api_key.get().strip()
        config_manager.set_api_key(provider.id, key)
        config_manager.set_ai_model(provider.id, self.entry_model.get())
        config_manager.ai_provider = provider.id
        self._on_status(f"{provider.name} API key saved" if key else f"{provider.name} API key removed")
