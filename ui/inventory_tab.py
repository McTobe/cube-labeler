#!/usr/bin/env python3
"""
Bin label editor for Brother PT-P300BT Label Studio.

Two kinds of bin label:
- Fasteners: size block, a name, one/two/four bins of lengths, and a drive icon
- Parts: a name banner, part number, note and an icon

The fields are in the same order as they appear on the printed label. The last label
made is remembered between sessions, so the next one starts from it.
"""

import copy
import os
import re
from dataclasses import asdict, fields
from tkinter import filedialog
from typing import Callable, Dict, Optional

import customtkinter as ctk

from core.config import config_manager
from core.inventory_renderer import ComponentLabelConfig, FastenerLabelConfig
from core.label_language import (
    LANGUAGES,
    build_presets,
    component_categories,
    fastener_categories,
    get_label_language,
    set_label_language,
)
from ui.icon_browser import IconBrowserDialog
from ui.widgets import MUTED_TEXT

KIND_FASTENER = "Fasteners"
KIND_PART = "Parts"

# Bins buttons -> compartment mode
BIN_MODES = {"One": "single", "Two": "dual", "Four": "quad"}

SIZES = ["M2", "M2.5", "M3", "M4", "M5", "M6", "M8", "M10", "M12"]

ICON_FROM_LIBRARY = "Icon from library…"
ICON_FROM_FILE = "Image file…"
NO_ICON = "None"

# Drive dropdown -> renderer tool_type
DRIVES = {
    "Hex socket (Allen)": "internal_hex",
    "Hex head": "external_hex",
    "Phillips (PH)": "phillips",
    "Pozidriv (PZ)": "pozidriv",
    "Torx": "torx",
    "Slotted": "slotted",
}
# Drives older labels may use but the dropdown no longer offers
LEGACY_DRIVES = {"Washer": "washer"}

# Part icon dropdown -> renderer icon_type
PART_ICONS = {
    "Ball bearing": "ball_bearing",
    "WAGO connector": "wago",
    "Fuse": "fuse",
}

LAST_LABEL_KEY = "last_bin_label"
SAVE_DELAY_MS = 800
MAX_FILE_NAME = 22

_NUMBER = re.compile(r"^\d+(?:[.,]\d+)?$")
_PREFIXED_NUMBER = re.compile(r"^[x×]\s*(\d+(?:[.,]\d+)?)$", re.IGNORECASE)


def format_length(text: str) -> str:
    """A plain number is a length and prints as "x30"; anything else prints as typed."""
    t = text.strip()
    return f"x{t}" if _NUMBER.match(t) else t


def unformat_length(text: str) -> str:
    """The form shows "x30" as just "30"."""
    t = text.strip()
    m = _PREFIXED_NUMBER.match(t)
    return m.group(1) if m else t


def _known_fields(cls, data: dict) -> dict:
    names = {f.name for f in fields(cls)}
    return {k: v for k, v in data.items() if k in names}


def _short_name(path: str) -> str:
    name = os.path.basename(path)
    return name if len(name) <= MAX_FILE_NAME else name[: MAX_FILE_NAME - 1] + "…"


def _to_editor_shape(cfg: FastenerLabelConfig) -> FastenerLabelConfig:
    """Older labels used an "assortment" layout and two note lines; the editor uses one bin plus one note."""
    cfg = copy.deepcopy(cfg)
    if cfg.compartment_mode == "assortment":
        cfg.compartment_mode = "single"
        cfg.length_single = cfg.assortment_line1
        cfg.standard_line1 = cfg.assortment_line2
        cfg.standard_line2 = ""
    elif cfg.standard_line2.strip():
        cfg.standard_line1 = f"{cfg.standard_line1} {cfg.standard_line2}".strip()
        cfg.standard_line2 = ""
    return cfg


class HardwareInventoryTab(ctk.CTkFrame):
    """Editor for fastener and part bin labels."""

    def __init__(self, master, on_change: Callable[[], None], on_add_queue: Callable[[], None], **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.on_change = on_change
        self.on_add_queue = on_add_queue
        self.language = get_label_language()

        defaults = build_presets(self.language)
        self.fastener_cfg = copy.deepcopy(defaults["A2"].config)
        self.component_cfg = copy.deepcopy(defaults["B1"].config)
        self.active_archetype = "fastener"  # "fastener" or "component"
        self._load_last_label()
        self.fastener_cfg = _to_editor_shape(self.fastener_cfg)

        self._updating_ui = False
        self._save_job = None
        self._setup_ui()
        self._show_kind(self.active_archetype)
        self._update_form_values()

    # =========================================================================
    # PUBLIC API (used by the main window)
    # =========================================================================

    def get_current_inventory_config(self):
        """Returns the label being edited (a copy)."""
        if self.active_archetype == "fastener":
            return copy.deepcopy(self.fastener_cfg)
        return copy.deepcopy(self.component_cfg)

    def load_inventory_config(self, cfg: object):
        """Opens a fastener or part label in the editor."""
        self._updating_ui = True
        try:
            if isinstance(cfg, FastenerLabelConfig):
                self.fastener_cfg = _to_editor_shape(cfg)
                self._show_kind("fastener")
            elif isinstance(cfg, ComponentLabelConfig):
                self.component_cfg = copy.deepcopy(cfg)
                self._show_kind("component")
            self._update_form_values()
        finally:
            self._updating_ui = False
        self._schedule_save()
        self.on_change()

    def set_language(self, lang: str):
        """Switches the language of the name suggestions (set in Settings)."""
        if lang not in LANGUAGES or lang == self.language:
            return
        set_label_language(lang)
        self.language = lang
        # Only the suggestions change; names already typed stay as they are
        self.entry_cat.configure(values=fastener_categories(lang))
        self.entry_banner_b.configure(values=component_categories(lang))

    # =========================================================================
    # LAYOUT
    # =========================================================================

    def _setup_ui(self):
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=12, pady=(4, 8))
        ctk.CTkLabel(top, text="Label for", text_color=MUTED_TEXT).pack(side="left", padx=(0, 8))
        self.kind_seg = ctk.CTkSegmentedButton(top, values=[KIND_FASTENER, KIND_PART], command=self._on_kind_changed)
        self.kind_seg.pack(side="left")

        ctk.CTkLabel(top, text="mm", text_color=MUTED_TEXT).pack(side="right")
        self.entry_width = ctk.CTkEntry(top, width=60)
        self.entry_width.pack(side="right", padx=(0, 6))
        self.entry_width.bind("<KeyRelease>", lambda e: self._on_field_change())
        ctk.CTkLabel(top, text="Label length", text_color=MUTED_TEXT).pack(side="right", padx=(0, 8))

        self.form_frame = ctk.CTkFrame(self, corner_radius=10)
        self.form_frame.pack(fill="x", padx=12, pady=(0, 8))
        self.frame_fastener = ctk.CTkFrame(self.form_frame, fg_color="transparent")
        self.frame_component = ctk.CTkFrame(self.form_frame, fg_color="transparent")
        self._build_fastener_form()
        self._build_component_form()

    def _row(self, parent, row: int, label: str, hint: str = "") -> ctk.CTkFrame:
        """One form row: label on the left, controls in the middle, an optional hint after them."""
        ctk.CTkLabel(parent, text=label, anchor="w").grid(row=row, column=0, sticky="nw", padx=(0, 14), pady=6)
        controls = ctk.CTkFrame(parent, fg_color="transparent")
        controls.grid(row=row, column=1, sticky="w", pady=6)
        if hint:
            ctk.CTkLabel(parent, text=hint, text_color=MUTED_TEXT, anchor="w").grid(
                row=row, column=2, sticky="w", padx=(12, 0), pady=6
            )
        return controls

    def _entry(self, parent, width: int, placeholder: str = "") -> ctk.CTkEntry:
        entry = ctk.CTkEntry(parent, width=width, placeholder_text=placeholder)
        entry.bind("<KeyRelease>", lambda e: self._on_field_change())
        return entry

    def _combo(self, parent, values, width: int, command=None) -> ctk.CTkComboBox:
        combo = ctk.CTkComboBox(parent, values=values, width=width, command=command or (lambda v: self._on_field_change()))
        combo.bind("<KeyRelease>", lambda e: self._on_field_change())
        return combo

    def _build_fastener_form(self):
        f = self.frame_fastener

        r = self._row(f, 0, "Size", "Or type your own, e.g. 1/4\" or #6-32")
        self.entry_thread = self._combo(r, SIZES, 100)
        self.entry_thread.pack(side="left")

        r = self._row(f, 1, "Name", "Type anything")
        self.entry_cat = self._combo(r, fastener_categories(self.language), 180)
        self.entry_cat.pack(side="left")

        r = self._row(f, 2, "Bins")
        self.mode_seg = ctk.CTkSegmentedButton(r, values=list(BIN_MODES), command=self._on_bins_changed)
        self.mode_seg.pack(side="left")

        r = self._row(f, 3, "Lengths", "Numbers print as x30")
        self.comp_inputs_frame = r

        r = self._row(f, 4, "Drive", "Size, e.g. 2.5, T20, PH2")
        self.drive_combo = ctk.CTkComboBox(
            r, values=self._drive_values(), width=180, state="readonly", command=self._on_drive_selected
        )
        self.drive_combo.pack(side="left")
        self.entry_tool_size = self._entry(r, 70)
        self.entry_tool_size.pack(side="left", padx=(8, 0))
        self.lbl_custom_tool_icon = ctk.CTkLabel(r, text="", text_color=MUTED_TEXT)
        self.lbl_custom_tool_icon.pack(side="left", padx=(8, 0))

    def _build_component_form(self):
        f = self.frame_component

        r = self._row(f, 0, "Name", "Type anything")
        self.entry_banner_b = self._combo(r, component_categories(self.language), 200)
        self.entry_banner_b.pack(side="left")

        r = self._row(f, 1, "Part number")
        self.entry_spec_pri = self._entry(r, 280, "e.g. 608ZZ")
        self.entry_spec_pri.pack(side="left")

        r = self._row(f, 2, "Note", "Optional")
        self.entry_spec_sec = self._entry(r, 280, "e.g. 0.2–4.0 mm²")
        self.entry_spec_sec.pack(side="left")

        r = self._row(f, 3, "Icon")
        self.part_icon_combo = ctk.CTkComboBox(
            r, values=self._part_icon_values(), width=200, state="readonly", command=self._on_part_icon_selected
        )
        self.part_icon_combo.pack(side="left")
        self.lbl_custom_comp_icon = ctk.CTkLabel(r, text="", text_color=MUTED_TEXT)
        self.lbl_custom_comp_icon.pack(side="left", padx=(8, 0))

    def _render_length_inputs(self):
        """Length boxes laid out like the bins on the label: one, two side by side, or a 2×2 grid."""
        for child in self.comp_inputs_frame.winfo_children():
            child.destroy()
        cfg = self.fastener_cfg
        mode = cfg.compartment_mode

        if mode == "single":
            self.entry_len_single = self._entry(self.comp_inputs_frame, 90, "20")
            self.entry_len_single.grid(row=0, column=0)
            self.entry_std_1 = self._entry(self.comp_inputs_frame, 170, "Note, e.g. DIN 933 8.8")
            self.entry_std_1.grid(row=0, column=1, padx=(8, 0))
            self._set_entry(self.entry_len_single, unformat_length(cfg.length_single))
            self._set_entry(self.entry_std_1, cfg.standard_line1)
        elif mode == "quad":
            self.entry_len_q1 = self._entry(self.comp_inputs_frame, 70)
            self.entry_len_q2 = self._entry(self.comp_inputs_frame, 70)
            self.entry_len_q3 = self._entry(self.comp_inputs_frame, 70)
            self.entry_len_q4 = self._entry(self.comp_inputs_frame, 70)
            self.entry_len_q1.grid(row=0, column=0, pady=(0, 4))
            self.entry_len_q2.grid(row=0, column=1, padx=(8, 0), pady=(0, 4))
            self.entry_len_q3.grid(row=1, column=0)
            self.entry_len_q4.grid(row=1, column=1, padx=(8, 0))
            for entry, value in (
                (self.entry_len_q1, cfg.length_quad_1),
                (self.entry_len_q2, cfg.length_quad_2),
                (self.entry_len_q3, cfg.length_quad_3),
                (self.entry_len_q4, cfg.length_quad_4),
            ):
                self._set_entry(entry, unformat_length(value))
        else:
            self.entry_len_dual_1 = self._entry(self.comp_inputs_frame, 70)
            self.entry_len_dual_2 = self._entry(self.comp_inputs_frame, 70)
            self.entry_len_dual_1.grid(row=0, column=0)
            self.entry_len_dual_2.grid(row=0, column=1, padx=(8, 0))
            self._set_entry(self.entry_len_dual_1, unformat_length(cfg.length_dual_1))
            self._set_entry(self.entry_len_dual_2, unformat_length(cfg.length_dual_2))

    @staticmethod
    def _set_entry(entry: ctk.CTkEntry, value: str):
        entry.delete(0, "end")
        if value:
            entry.insert(0, value)

    # =========================================================================
    # DROPDOWN CONTENTS
    # =========================================================================

    def _drive_values(self):
        values = list(DRIVES) + [NO_ICON]
        legacy = next((name for name, t in LEGACY_DRIVES.items() if t == self.fastener_cfg.tool_type), None)
        if legacy:
            values.append(legacy)
        return values + [ICON_FROM_LIBRARY, ICON_FROM_FILE]

    def _drive_display(self) -> str:
        t = self.fastener_cfg.tool_type
        for name, tool_type in {**DRIVES, **LEGACY_DRIVES}.items():
            if tool_type == t:
                return name
        if t == "custom" and self.fastener_cfg.custom_tool_icon_path:
            return ICON_FROM_LIBRARY
        return NO_ICON

    def _part_icon_values(self):
        return list(PART_ICONS) + [NO_ICON, ICON_FROM_LIBRARY, ICON_FROM_FILE]

    def _part_icon_display(self) -> str:
        t = self.component_cfg.icon_type
        for name, icon_type in PART_ICONS.items():
            if icon_type == t:
                return name
        if t == "custom" and self.component_cfg.custom_icon_path:
            return ICON_FROM_LIBRARY
        return NO_ICON

    # =========================================================================
    # EVENTS
    # =========================================================================

    def _show_kind(self, kind: str):
        self.active_archetype = kind
        if kind == "fastener":
            self.kind_seg.set(KIND_FASTENER)
            self.frame_component.pack_forget()
            self.frame_fastener.pack(fill="x", padx=14, pady=8)
        else:
            self.kind_seg.set(KIND_PART)
            self.frame_fastener.pack_forget()
            self.frame_component.pack(fill="x", padx=14, pady=8)

    def _on_kind_changed(self, value: str):
        self._collect_form_values()
        self._show_kind("fastener" if value == KIND_FASTENER else "component")
        self._updating_ui = True
        try:
            self._update_form_values()
        finally:
            self._updating_ui = False
        self._schedule_save()
        self.on_change()

    def _on_bins_changed(self, value: str):
        self._collect_form_values()
        self.fastener_cfg.compartment_mode = BIN_MODES.get(value, "dual")
        self._render_length_inputs()
        self._on_field_change()

    def _on_drive_selected(self, value: str):
        if value in (ICON_FROM_LIBRARY, ICON_FROM_FILE):
            self._choose_icon(value, self._set_tool_icon_path, "Fasteners")
            # Until an icon is chosen, keep showing the current drive
            self.drive_combo.set(self._drive_display())
            return
        self.fastener_cfg.tool_type = {**DRIVES, **LEGACY_DRIVES}.get(value, "none")
        self.fastener_cfg.custom_tool_icon_path = None
        self.lbl_custom_tool_icon.configure(text="")
        self._on_field_change()

    def _on_part_icon_selected(self, value: str):
        if value in (ICON_FROM_LIBRARY, ICON_FROM_FILE):
            self._choose_icon(value, self._set_comp_icon_path, "Engineering")
            self.part_icon_combo.set(self._part_icon_display())
            return
        self.component_cfg.icon_type = PART_ICONS.get(value, "none")
        self.component_cfg.custom_icon_path = None
        self.lbl_custom_comp_icon.configure(text="")
        self._on_field_change()

    def _choose_icon(self, source: str, on_chosen: Callable[[str], None], category: str):
        if source == ICON_FROM_LIBRARY:
            IconBrowserDialog(self, on_select=on_chosen, initial_category=category, title_suffix="Bin label icon")
        else:
            path = filedialog.askopenfilename(
                title="Choose an icon image",
                filetypes=[("Images", "*.png;*.jpg;*.jpeg;*.bmp;*.webp;*.ico"), ("All files", "*.*")],
            )
            if path:
                on_chosen(path)

    def _set_tool_icon_path(self, path: str):
        if path and os.path.isfile(path):
            self.fastener_cfg.tool_type = "custom"
            self.fastener_cfg.custom_tool_icon_path = path
            self.drive_combo.set(ICON_FROM_LIBRARY)
            self.lbl_custom_tool_icon.configure(text=_short_name(path))
            self._schedule_save()
            self.on_change()

    def _set_comp_icon_path(self, path: str):
        if path and os.path.isfile(path):
            self.component_cfg.icon_type = "custom"
            self.component_cfg.custom_icon_path = path
            self.part_icon_combo.set(ICON_FROM_LIBRARY)
            self.lbl_custom_comp_icon.configure(text=_short_name(path))
            self._schedule_save()
            self.on_change()

    def _on_field_change(self):
        if self._updating_ui:
            return
        self._collect_form_values()
        self._schedule_save()
        self.on_change()

    # =========================================================================
    # FORM <-> CONFIG
    # =========================================================================

    def _width_value(self) -> float:
        try:
            return max(float(self.entry_width.get().strip().replace(",", ".")), 10.0)
        except ValueError:
            return 38.0

    def _collect_form_values(self):
        """Reads the form into the label being edited."""
        if self.active_archetype == "fastener":
            cfg = self.fastener_cfg
            cfg.thread_size = self.entry_thread.get().strip() or "M3"
            cfg.category = self.entry_cat.get().strip()
            cfg.label_width_mm = self._width_value()
            cfg.tool_size = self.entry_tool_size.get().strip()

            mode = cfg.compartment_mode
            if mode == "single" and hasattr(self, "entry_len_single"):
                cfg.length_single = format_length(self.entry_len_single.get())
                cfg.standard_line1 = self.entry_std_1.get().strip()
                cfg.standard_line2 = ""
            elif mode == "dual" and hasattr(self, "entry_len_dual_1"):
                cfg.length_dual_1 = format_length(self.entry_len_dual_1.get())
                cfg.length_dual_2 = format_length(self.entry_len_dual_2.get())
            elif mode == "quad" and hasattr(self, "entry_len_q1"):
                cfg.length_quad_1 = format_length(self.entry_len_q1.get())
                cfg.length_quad_2 = format_length(self.entry_len_q2.get())
                cfg.length_quad_3 = format_length(self.entry_len_q3.get())
                cfg.length_quad_4 = format_length(self.entry_len_q4.get())
        else:
            cfg = self.component_cfg
            cfg.category_banner = self.entry_banner_b.get().strip()
            cfg.spec_primary = self.entry_spec_pri.get().strip()
            cfg.spec_secondary = self.entry_spec_sec.get().strip()
            cfg.label_width_mm = self._width_value()

    def _update_form_values(self):
        """Fills the form from the label being edited."""
        if self.active_archetype == "fastener":
            cfg = self.fastener_cfg
            self.entry_thread.set(cfg.thread_size)
            self.entry_cat.set(cfg.category)
            self._set_entry(self.entry_width, f"{cfg.label_width_mm:g}")
            mode_name = next((n for n, m in BIN_MODES.items() if m == cfg.compartment_mode), "Two")
            self.mode_seg.set(mode_name)
            self._render_length_inputs()
            self.drive_combo.configure(values=self._drive_values())
            self.drive_combo.set(self._drive_display())
            self._set_entry(self.entry_tool_size, cfg.tool_size)
            self.lbl_custom_tool_icon.configure(
                text=_short_name(cfg.custom_tool_icon_path) if cfg.tool_type == "custom" and cfg.custom_tool_icon_path else ""
            )
        else:
            cfg = self.component_cfg
            self.entry_banner_b.set(cfg.category_banner)
            self._set_entry(self.entry_width, f"{cfg.label_width_mm:g}")
            self._set_entry(self.entry_spec_pri, cfg.spec_primary)
            self._set_entry(self.entry_spec_sec, cfg.spec_secondary)
            self.part_icon_combo.set(self._part_icon_display())
            self.lbl_custom_comp_icon.configure(
                text=_short_name(cfg.custom_icon_path) if cfg.icon_type == "custom" and cfg.custom_icon_path else ""
            )

    # =========================================================================
    # REMEMBER THE LAST LABEL
    # =========================================================================

    def _load_last_label(self):
        data = config_manager.get(LAST_LABEL_KEY)
        if not isinstance(data, dict):
            return
        try:
            if isinstance(data.get("fastener"), dict):
                self.fastener_cfg = FastenerLabelConfig(**_known_fields(FastenerLabelConfig, data["fastener"]))
            if isinstance(data.get("part"), dict):
                self.component_cfg = ComponentLabelConfig(**_known_fields(ComponentLabelConfig, data["part"]))
            if data.get("kind") in ("fastener", "component"):
                self.active_archetype = data["kind"]
        except (TypeError, ValueError):
            pass

    def _schedule_save(self):
        """Saves shortly after the last change, so typing doesn't write the settings file on every key."""
        if self._save_job is not None:
            try:
                self.after_cancel(self._save_job)
            except Exception:
                pass
        self._save_job = self.after(SAVE_DELAY_MS, self.save_last_label)

    def save_last_label(self):
        self._save_job = None
        config_manager.set(
            LAST_LABEL_KEY,
            {
                "kind": self.active_archetype,
                "fastener": asdict(self.fastener_cfg),
                "part": asdict(self.component_cfg),
            },
        )
