#!/usr/bin/env python3
"""
Hardware & Bins UI Tab for Brother PT-P300BT Label Studio.
Provides an interactive builder for the V2 Hardware Inventory Label Design System:
- Archetype A: Threaded Fasteners (Screws, Nuts, Washers)
- Archetype B: Discrete Components & Electrical Hardware
"""

import copy
import os
from tkinter import filedialog
import customtkinter as ctk
from typing import Callable, Optional
from core.inventory_renderer import (
    FastenerLabelConfig,
    ComponentLabelConfig,
)
from core.label_language import (
    LANGUAGES,
    build_presets,
    component_categories,
    fastener_categories,
    get_label_language,
    set_label_language,
)

TYPE_FASTENER = "Screws and nuts"
TYPE_COMPONENT = "Components"

# Compartment modes and the names shown on the layout buttons
MODE_LABELS = {
    "single": "One size",
    "dual": "Two bins",
    "quad": "Four bins (2×2)",
    "assortment": "Mixed sizes",
}

# Names for the built-in icons that presets use
TOOL_ICON_NAMES = {
    "internal_hex": "Socket (hex)",
    "external_hex": "Hex head",
    "washer": "Washer",
    "torx": "Torx",
    "phillips": "Phillips",
    "slotted": "Slotted",
}
COMPONENT_ICON_NAMES = {
    "ball_bearing": "Ball bearing",
    "wago": "WAGO connector",
    "fuse": "Fuse",
}

# Long file names would push the rest of the icon row out of view
MAX_ICON_NAME = 24


def _short_name(path: str) -> str:
    name = os.path.basename(path)
    return name if len(name) <= MAX_ICON_NAME else name[: MAX_ICON_NAME - 1] + "…"


from ui.icon_browser import IconBrowserDialog
from ui.ai_generator_dialog import AIGeneratorDialog


class HardwareInventoryTab(ctk.CTkFrame):
    """Interactive editor for V2 Hardware Inventory bin labels."""

    def __init__(self, master, on_change: Callable[[], None], on_add_queue: Callable[[], None], **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)

        self.on_change = on_change
        self.on_add_queue = on_add_queue

        self.active_archetype = "fastener"  # "fastener" (Archetype A) or "component" (Archetype B)
        self.language = get_label_language()
        self.presets = build_presets(self.language)
        self.fastener_cfg = copy.deepcopy(self.presets["A2"].config)
        self.component_cfg = copy.deepcopy(self.presets["B1"].config)

        self._updating_ui = False
        self._setup_ui()
        self._update_form_values()

    def get_current_inventory_config(self):
        """Returns active FastenerLabelConfig or ComponentLabelConfig."""
        if self.active_archetype == "fastener":
            return copy.deepcopy(self.fastener_cfg)
        else:
            return copy.deepcopy(self.component_cfg)

    def load_inventory_config(self, cfg: object):
        """Loads a FastenerLabelConfig or ComponentLabelConfig into the UI."""
        self._updating_ui = True
        try:
            if isinstance(cfg, FastenerLabelConfig):
                self.active_archetype = "fastener"
                self.fastener_cfg = copy.deepcopy(cfg)
                self.archetype_seg.set(TYPE_FASTENER)
                self.frame_component.pack_forget()
                self.frame_fastener.pack(fill="both", expand=True, padx=12, pady=10)
            elif isinstance(cfg, ComponentLabelConfig):
                self.active_archetype = "component"
                self.component_cfg = copy.deepcopy(cfg)
                self.archetype_seg.set(TYPE_COMPONENT)
                self.frame_fastener.pack_forget()
                self.frame_component.pack(fill="both", expand=True, padx=12, pady=10)
            self._update_form_values()
        finally:
            self._updating_ui = False
        self.on_change()

    def _setup_ui(self):
        # 1. Top Controls Bar: Archetype Switcher & Preset Quick-Loader
        top_bar = ctk.CTkFrame(self, fg_color="transparent")
        top_bar.pack(fill="x", padx=12, pady=(8, 10))

        # Archetype Switcher
        ctk.CTkLabel(top_bar, text="Label type", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left", padx=(0, 6))
        self.archetype_seg = ctk.CTkSegmentedButton(
            top_bar,
            values=[TYPE_FASTENER, TYPE_COMPONENT],
            command=self._on_archetype_switch,
        )
        self.archetype_seg.set(TYPE_FASTENER)
        self.archetype_seg.pack(side="left", padx=4)

        # Preset Quick-Loader
        ctk.CTkLabel(top_bar, text="Presets").pack(side="left", padx=(25, 6))
        self.preset_combo = ctk.CTkComboBox(
            top_bar,
            values=[p.name for p in self.presets.values()],
            width=270,
            command=self._on_preset_selected,
        )
        self.preset_combo.set(self.presets["A2"].name)
        self.preset_combo.pack(side="left", padx=4)

        # 2. Form Container Frame
        self.form_frame = ctk.CTkFrame(self, corner_radius=8)
        self.form_frame.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        # Sub-frames for Archetype A and Archetype B
        self.frame_fastener = ctk.CTkFrame(self.form_frame, fg_color="transparent")
        self.frame_component = ctk.CTkFrame(self.form_frame, fg_color="transparent")

        self._build_fastener_form()
        self._build_component_form()

        # Show initial form
        self.frame_fastener.pack(fill="both", expand=True, padx=12, pady=10)

    # =========================================================================
    # ARCHETYPE A FORM: THREADED FASTENERS
    # =========================================================================

    def _form_row(self, parent, row: int, label: str, pady=(4, 4)) -> ctk.CTkFrame:
        """A form row: a bold label in the first column and a frame for the controls."""
        ctk.CTkLabel(parent, text=label, font=ctk.CTkFont(weight="bold"), anchor="w").grid(
            row=row, column=0, sticky="w", padx=(0, 12), pady=pady
        )
        controls = ctk.CTkFrame(parent, fg_color="transparent")
        controls.grid(row=row, column=1, sticky="w", pady=pady)
        return controls

    def _build_fastener_form(self):
        f = self.frame_fastener

        # Size, category and label length
        r1 = self._form_row(f, 0, "Size")
        self.entry_thread = ctk.CTkComboBox(
            r1,
            values=["M2", "M2.5", "M3", "M4", "M5", "M6", "M8", "M10", "M12", "1/4\"", "#6-32"],
            width=90,
            command=lambda v: self._on_field_change(),
        )
        self.entry_thread.set("M3")
        self.entry_thread.pack(side="left")
        self.entry_thread.bind("<KeyRelease>", lambda e: self._on_field_change())

        ctk.CTkLabel(r1, text="Category").pack(side="left", padx=(20, 6))
        self.entry_cat = ctk.CTkComboBox(
            r1,
            values=fastener_categories(self.language),
            width=150,
            command=lambda v: self._on_field_change(),
        )
        self.entry_cat.set(fastener_categories(self.language)[0])
        self.entry_cat.pack(side="left")
        self.entry_cat.bind("<KeyRelease>", lambda e: self._on_field_change())

        ctk.CTkLabel(r1, text="Label length (mm)").pack(side="left", padx=(20, 6))
        self.entry_width_a = ctk.CTkEntry(r1, width=70)
        self.entry_width_a.insert(0, "38")
        self.entry_width_a.pack(side="left")
        self.entry_width_a.bind("<KeyRelease>", lambda e: self._on_field_change())

        # Compartment layout
        r2 = self._form_row(f, 1, "Layout", pady=(10, 4))
        self.mode_seg = ctk.CTkSegmentedButton(
            r2,
            values=list(MODE_LABELS.values()),
            command=self._on_comp_mode_changed,
        )
        self.mode_seg.set(MODE_LABELS["dual"])
        self.mode_seg.pack(side="left")

        # Inputs for the chosen layout, lined up under the layout buttons
        self.comp_inputs_frame = ctk.CTkFrame(f, fg_color="transparent")
        self.comp_inputs_frame.grid(row=2, column=1, sticky="w", pady=(4, 6))

        # Tool icon and size
        r4 = self._form_row(f, 3, "Tool icon", pady=(8, 4))
        self.btn_pick_tool_icon = ctk.CTkButton(
            r4,
            text="Choose file…",
            width=100,
            command=self._on_browse_custom_tool_icon,
        )
        self.btn_pick_tool_icon.pack(side="left", padx=(0, 6))

        self.btn_lib_tool_icon = ctk.CTkButton(
            r4,
            text="Icon library…",
            width=100,
            command=self._on_open_tool_library,
        )
        self.btn_lib_tool_icon.pack(side="left", padx=(0, 8))

        self.lbl_custom_tool_icon = ctk.CTkLabel(
            r4,
            text="No icon chosen",
            text_color="gray",
        )
        self.lbl_custom_tool_icon.pack(side="left", padx=4)

        self.btn_clear_tool_icon = ctk.CTkButton(
            r4,
            text="Clear",
            width=60,
            fg_color="gray40",
            hover_color="gray30",
            command=self._on_clear_custom_tool_icon,
        )
        self.btn_clear_tool_icon.pack(side="left", padx=(4, 16))

        ctk.CTkLabel(r4, text="Tool size").pack(side="left", padx=(0, 6))
        self.entry_tool_size = ctk.CTkEntry(r4, width=60)
        self.entry_tool_size.insert(0, "2.5")
        self.entry_tool_size.pack(side="left")
        self.entry_tool_size.bind("<KeyRelease>", lambda e: self._on_field_change())

    def _comp_input(self, label: str, value: str, width: int, first: bool = False) -> ctk.CTkEntry:
        """A label and entry inside the layout inputs row."""
        ctk.CTkLabel(self.comp_inputs_frame, text=label).pack(side="left", padx=(0 if first else 16, 6))
        entry = ctk.CTkEntry(self.comp_inputs_frame, width=width)
        entry.insert(0, value)
        entry.pack(side="left")
        entry.bind("<KeyRelease>", lambda e: self._on_field_change())
        return entry

    def _render_dynamic_comp_inputs(self):
        """Builds input fields corresponding to the selected compartment mode."""
        for c in self.comp_inputs_frame.winfo_children():
            c.destroy()

        cfg = self.fastener_cfg
        mode = cfg.compartment_mode

        if mode == "single":
            self.entry_len_single = self._comp_input("Length", cfg.length_single, 80, first=True)
            self.entry_std_1 = self._comp_input("Line 1", cfg.standard_line1, 110)
            self.entry_std_2 = self._comp_input("Line 2", cfg.standard_line2, 110)

        elif mode == "dual":
            self.entry_len_dual_1 = self._comp_input("Left bin length", cfg.length_dual_1, 80, first=True)
            self.entry_len_dual_2 = self._comp_input("Right bin length", cfg.length_dual_2, 80)

        elif mode == "quad":
            self.entry_len_q1 = self._comp_input("Top left", cfg.length_quad_1, 60, first=True)
            self.entry_len_q2 = self._comp_input("Top right", cfg.length_quad_2, 60)
            self.entry_len_q3 = self._comp_input("Bottom left", cfg.length_quad_3, 60)
            self.entry_len_q4 = self._comp_input("Bottom right", cfg.length_quad_4, 60)

        elif mode == "assortment":
            self.entry_assort_1 = self._comp_input("Line 1", cfg.assortment_line1, 140, first=True)
            self.entry_assort_2 = self._comp_input("Line 2", cfg.assortment_line2, 140)

    # =========================================================================
    # ARCHETYPE B FORM: DISCRETE COMPONENTS & ELECTRICAL HARDWARE
    # =========================================================================

    def _build_component_form(self):
        f = self.frame_component

        # Category and label length
        r1 = self._form_row(f, 0, "Category")
        self.r1_comp = r1
        self.entry_banner_b = ctk.CTkComboBox(
            r1,
            values=component_categories(self.language),
            width=180,
            command=lambda v: self._on_field_change(),
        )
        self.entry_banner_b.set(component_categories(self.language)[0])
        self.entry_banner_b.pack(side="left")
        self.entry_banner_b.bind("<KeyRelease>", lambda e: self._on_field_change())

        ctk.CTkLabel(r1, text="Label length (mm)").pack(side="left", padx=(20, 6))
        self.entry_width_b = ctk.CTkEntry(r1, width=70)
        self.entry_width_b.insert(0, "38")
        self.entry_width_b.pack(side="left")
        self.entry_width_b.bind("<KeyRelease>", lambda e: self._on_field_change())

        # Icon on the right of the label
        r_icon = self._form_row(f, 1, "Icon", pady=(4, 6))
        self.btn_pick_comp_icon = ctk.CTkButton(
            r_icon,
            text="Choose file…",
            width=100,
            command=self._on_browse_custom_comp_icon,
        )
        self.btn_pick_comp_icon.pack(side="left", padx=(0, 6))

        self.btn_lib_comp_icon = ctk.CTkButton(
            r_icon,
            text="Icon library…",
            width=100,
            command=self._on_open_comp_library,
        )
        self.btn_lib_comp_icon.pack(side="left", padx=(0, 8))

        self.lbl_custom_comp_icon = ctk.CTkLabel(
            r_icon,
            text="No icon chosen",
            text_color="gray",
        )
        self.lbl_custom_comp_icon.pack(side="left", padx=4)

        self.btn_clear_comp_icon = ctk.CTkButton(
            r_icon,
            text="Clear",
            width=60,
            fg_color="gray40",
            hover_color="gray30",
            command=self._on_clear_custom_comp_icon,
        )
        self.btn_clear_comp_icon.pack(side="left", padx=4)

        # Main line
        r2 = self._form_row(f, 2, "Part or model", pady=(10, 4))
        self.entry_spec_pri = ctk.CTkEntry(r2, width=300)
        self.entry_spec_pri.insert(0, "608ZZ")
        self.entry_spec_pri.pack(side="left")
        self.entry_spec_pri.bind("<KeyRelease>", lambda e: self._on_field_change())

        # Second line
        r3 = self._form_row(f, 3, "Notes", pady=(6, 4))
        self.entry_spec_sec = ctk.CTkEntry(r3, width=300, placeholder_text="Optional, e.g. 0.2–4.0 mm², inline")
        self.entry_spec_sec.pack(side="left")
        self.entry_spec_sec.bind("<KeyRelease>", lambda e: self._on_field_change())

    # =========================================================================
    # EVENT HANDLERS
    # =========================================================================

    def _on_archetype_switch(self, value: str):
        if value == TYPE_FASTENER:
            self.active_archetype = "fastener"
            self.frame_component.pack_forget()
            self.frame_fastener.pack(fill="both", expand=True, padx=12, pady=10)
        else:
            self.active_archetype = "component"
            self.frame_fastener.pack_forget()
            self.frame_component.pack(fill="both", expand=True, padx=12, pady=10)
        self._collect_form_values()
        self.on_change()

    def _find_preset(self, id_or_name: str):
        """Accepts a preset id ("A2") or the name shown in the dropdown."""
        if id_or_name in self.presets:
            return self.presets[id_or_name]
        for p in self.presets.values():
            if p.name == id_or_name:
                return p
        return None

    def set_language(self, lang: str):
        """Switches the language of category suggestions and presets (set in Settings)."""
        if lang not in LANGUAGES or lang == self.language:
            return
        set_label_language(lang)
        self.language = lang
        self.presets = build_presets(lang)
        # Only the suggestions change; text already on the current label stays as typed
        self.preset_combo.configure(values=[p.name for p in self.presets.values()])
        self.entry_cat.configure(values=fastener_categories(lang))
        self.entry_banner_b.configure(values=component_categories(lang))

    def _on_preset_selected(self, name: str):
        found = self._find_preset(name)
        if not found:
            return
        preset = found.config
        self.preset_combo.set(found.name)

        self._updating_ui = True
        try:
            if isinstance(preset, FastenerLabelConfig):
                self.active_archetype = "fastener"
                self.fastener_cfg = copy.deepcopy(preset)
                self.archetype_seg.set(TYPE_FASTENER)
                self.frame_component.pack_forget()
                self.frame_fastener.pack(fill="both", expand=True, padx=12, pady=10)
            else:
                self.active_archetype = "component"
                self.component_cfg = copy.deepcopy(preset)
                self.archetype_seg.set(TYPE_COMPONENT)
                self.frame_fastener.pack_forget()
                self.frame_component.pack(fill="both", expand=True, padx=12, pady=10)

            self._update_form_values()
        finally:
            self._updating_ui = False

        self.on_change()

    def _on_comp_mode_changed(self, value: str):
        mode_map = {label: mode for mode, label in MODE_LABELS.items()}
        self.fastener_cfg.compartment_mode = mode_map.get(value, "dual")
        self._render_dynamic_comp_inputs()
        self._on_field_change()

    def _on_browse_custom_tool_icon(self):
        path = filedialog.askopenfilename(
            title="Choose a tool icon",
            filetypes=[
                ("Images", "*.png;*.jpg;*.jpeg;*.bmp;*.webp;*.ico"),
                ("All files", "*.*"),
            ],
        )
        if path:
            self._set_tool_icon_path(path)

    def _set_tool_icon_path(self, path: str):
        if path and os.path.isfile(path):
            self.fastener_cfg.custom_tool_icon_path = path
            self.fastener_cfg.tool_type = "custom"
            self.lbl_custom_tool_icon.configure(text=_short_name(path), text_color=("gray10", "gray90"))
            self.on_change()

    def _on_open_tool_library(self):
        IconBrowserDialog(
            self,
            on_select=self._set_tool_icon_path,
            initial_category="Fasteners",
            title_suffix="Tool icon",
        )

    def _on_clear_custom_tool_icon(self):
        self.fastener_cfg.custom_tool_icon_path = None
        self.fastener_cfg.tool_type = "none"
        self.lbl_custom_tool_icon.configure(text="No icon chosen", text_color="gray")
        self.on_change()

    def _on_browse_custom_comp_icon(self):
        path = filedialog.askopenfilename(
            title="Choose a component icon",
            filetypes=[
                ("Images", "*.png;*.jpg;*.jpeg;*.bmp;*.webp;*.ico"),
                ("All files", "*.*"),
            ],
        )
        if path:
            self._set_comp_icon_path(path)

    def _set_comp_icon_path(self, path: str):
        if path and os.path.isfile(path):
            self.component_cfg.custom_icon_path = path
            self.component_cfg.icon_type = "custom"
            self.lbl_custom_comp_icon.configure(text=_short_name(path), text_color=("gray10", "gray90"))
            self.on_change()

    def _on_open_comp_library(self):
        IconBrowserDialog(
            self,
            on_select=self._set_comp_icon_path,
            initial_category="Engineering",
            title_suffix="Component icon",
        )

    def _on_clear_custom_comp_icon(self):
        self.component_cfg.custom_icon_path = None
        self.component_cfg.icon_type = "none"
        self.lbl_custom_comp_icon.configure(text="No icon chosen", text_color="gray")
        self.on_change()

    def _on_field_change(self):
        if self._updating_ui:
            return
        self._collect_form_values()
        self.on_change()

    def _collect_form_values(self):
        """Reads widget values into active configuration object."""
        if self.active_archetype == "fastener":
            self.fastener_cfg.thread_size = self.entry_thread.get().strip() or "M3"
            self.fastener_cfg.category = self.entry_cat.get().strip() or fastener_categories(self.language)[0]
            try:
                self.fastener_cfg.label_width_mm = float(self.entry_width_a.get().strip())
            except ValueError:
                self.fastener_cfg.label_width_mm = 38.0

            self.fastener_cfg.tool_size = self.entry_tool_size.get().strip()

            mode = self.fastener_cfg.compartment_mode
            if mode == "single":
                if hasattr(self, "entry_len_single"):
                    self.fastener_cfg.length_single = self.entry_len_single.get()
                if hasattr(self, "entry_std_1"):
                    self.fastener_cfg.standard_line1 = self.entry_std_1.get()
                if hasattr(self, "entry_std_2"):
                    self.fastener_cfg.standard_line2 = self.entry_std_2.get()
            elif mode == "dual":
                if hasattr(self, "entry_len_dual_1"):
                    self.fastener_cfg.length_dual_1 = self.entry_len_dual_1.get()
                if hasattr(self, "entry_len_dual_2"):
                    self.fastener_cfg.length_dual_2 = self.entry_len_dual_2.get()
            elif mode == "quad":
                if hasattr(self, "entry_len_q1"):
                    self.fastener_cfg.length_quad_1 = self.entry_len_q1.get()
                if hasattr(self, "entry_len_q2"):
                    self.fastener_cfg.length_quad_2 = self.entry_len_q2.get()
                if hasattr(self, "entry_len_q3"):
                    self.fastener_cfg.length_quad_3 = self.entry_len_q3.get()
                if hasattr(self, "entry_len_q4"):
                    self.fastener_cfg.length_quad_4 = self.entry_len_q4.get()
            elif mode == "assortment":
                if hasattr(self, "entry_assort_1"):
                    self.fastener_cfg.assortment_line1 = self.entry_assort_1.get()
                if hasattr(self, "entry_assort_2"):
                    self.fastener_cfg.assortment_line2 = self.entry_assort_2.get()

        else:
            self.component_cfg.category_banner = self.entry_banner_b.get().strip() or component_categories(self.language)[0]
            self.component_cfg.spec_primary = self.entry_spec_pri.get().strip() or "608ZZ"
            self.component_cfg.spec_secondary = self.entry_spec_sec.get().strip()
            try:
                self.component_cfg.label_width_mm = float(self.entry_width_b.get().strip())
            except ValueError:
                self.component_cfg.label_width_mm = 38.0

    def _update_form_values(self):
        """Populates form widgets from active configuration object."""
        if self.active_archetype == "fastener":
            self.entry_thread.set(self.fastener_cfg.thread_size)
            self.entry_cat.set(self.fastener_cfg.category)
            self.entry_width_a.delete(0, "end")
            self.entry_width_a.insert(0, str(self.fastener_cfg.label_width_mm))

            self.mode_seg.set(MODE_LABELS.get(self.fastener_cfg.compartment_mode, MODE_LABELS["dual"]))
            self._render_dynamic_comp_inputs()

            self.entry_tool_size.delete(0, "end")
            self.entry_tool_size.insert(0, self.fastener_cfg.tool_size)

            if self.fastener_cfg.custom_tool_icon_path:
                self.lbl_custom_tool_icon.configure(
                    text=_short_name(self.fastener_cfg.custom_tool_icon_path),
                    text_color=("gray10", "gray90"),
                )
            elif self.fastener_cfg.tool_type and self.fastener_cfg.tool_type not in ("none", "custom"):
                self.lbl_custom_tool_icon.configure(
                    text=TOOL_ICON_NAMES.get(self.fastener_cfg.tool_type, self.fastener_cfg.tool_type),
                    text_color=("gray10", "gray90"),
                )
            else:
                self.lbl_custom_tool_icon.configure(text="No icon chosen", text_color="gray")

        else:
            self.entry_banner_b.set(self.component_cfg.category_banner)
            self.entry_width_b.delete(0, "end")
            self.entry_width_b.insert(0, str(self.component_cfg.label_width_mm))

            self.entry_spec_pri.delete(0, "end")
            self.entry_spec_pri.insert(0, self.component_cfg.spec_primary)
            self.entry_spec_sec.delete(0, "end")
            self.entry_spec_sec.insert(0, self.component_cfg.spec_secondary)

            if self.component_cfg.custom_icon_path:
                self.lbl_custom_comp_icon.configure(
                    text=_short_name(self.component_cfg.custom_icon_path),
                    text_color=("gray10", "gray90"),
                )
            elif self.component_cfg.icon_type and self.component_cfg.icon_type not in ("none", "custom"):
                self.lbl_custom_comp_icon.configure(
                    text=COMPONENT_ICON_NAMES.get(self.component_cfg.icon_type, self.component_cfg.icon_type),
                    text_color=("gray10", "gray90"),
                )
            else:
                self.lbl_custom_comp_icon.configure(text="No icon chosen", text_color="gray")
