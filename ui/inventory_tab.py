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

        # Language of the printed label text (the app itself stays English)
        self.language_combo = ctk.CTkComboBox(
            top_bar,
            values=list(LANGUAGES.values()),
            width=110,
            command=self._on_language_changed,
        )
        self.language_combo.set(LANGUAGES[self.language])
        self.language_combo.pack(side="right", padx=4)
        ctk.CTkLabel(top_bar, text="Label language").pack(side="right", padx=(25, 6))

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

    def _build_fastener_form(self):
        f = self.frame_fastener

        # Row 1: Thread Size, Category, Width
        r1 = ctk.CTkFrame(f, fg_color="transparent")
        r1.pack(fill="x", pady=4)

        ctk.CTkLabel(r1, text="Size", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(0, 6))
        self.entry_thread = ctk.CTkComboBox(
            r1,
            values=["M2", "M2.5", "M3", "M4", "M5", "M6", "M8", "M10", "M12", "1/4\"", "#6-32"],
            width=90,
            command=lambda v: self._on_field_change(),
        )
        self.entry_thread.set("M3")
        self.entry_thread.pack(side="left", padx=4)
        self.entry_thread.bind("<KeyRelease>", lambda e: self._on_field_change())

        ctk.CTkLabel(r1, text="Category").pack(side="left", padx=(20, 6))
        self.entry_cat = ctk.CTkComboBox(
            r1,
            values=fastener_categories(self.language),
            width=150,
            command=lambda v: self._on_field_change(),
        )
        self.entry_cat.set(fastener_categories(self.language)[0])
        self.entry_cat.pack(side="left", padx=4)
        self.entry_cat.bind("<KeyRelease>", lambda e: self._on_field_change())

        ctk.CTkLabel(r1, text="Label length (mm)").pack(side="left", padx=(20, 6))
        self.entry_width_a = ctk.CTkEntry(r1, width=70)
        self.entry_width_a.insert(0, "38")
        self.entry_width_a.pack(side="left", padx=4)
        self.entry_width_a.bind("<KeyRelease>", lambda e: self._on_field_change())

        # Row 2: Compartment Mode Selector
        r2 = ctk.CTkFrame(f, fg_color="transparent")
        r2.pack(fill="x", pady=(10, 4))

        ctk.CTkLabel(r2, text="Layout", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(0, 6))
        self.mode_seg = ctk.CTkSegmentedButton(
            r2,
            values=["Single Size", "2-Bin (Dual)", "4-Bin (2×2 Grid)", "Assortment Text"],
            command=self._on_comp_mode_changed,
        )
        self.mode_seg.set("2-Bin (Dual)")
        self.mode_seg.pack(side="left", padx=4)

        # Row 3: Dynamic Compartment Inputs Container
        self.comp_inputs_frame = ctk.CTkFrame(f, fg_color="transparent")
        self.comp_inputs_frame.pack(fill="x", pady=6)

        # Row 4: Tool Drive Badge (Icon + Size)
        r4 = ctk.CTkFrame(f, fg_color="transparent")
        r4.pack(fill="x", pady=(8, 4))

        ctk.CTkLabel(r4, text="Tool icon", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(0, 8))

        self.btn_pick_tool_icon = ctk.CTkButton(
            r4,
            text="🖼 Choose File...",
            width=120,
            command=self._on_browse_custom_tool_icon,
        )
        self.btn_pick_tool_icon.pack(side="left", padx=(0, 6))

        self.btn_lib_tool_icon = ctk.CTkButton(
            r4,
            text="📚 Library...",
            width=100,
            fg_color="#0284C7",
            hover_color="#0369A1",
            command=self._on_open_tool_library,
        )
        self.btn_lib_tool_icon.pack(side="left", padx=(0, 6))

        self.lbl_custom_tool_icon = ctk.CTkLabel(
            r4,
            text="No icon chosen",
            text_color="gray",
        )
        self.lbl_custom_tool_icon.pack(side="left", padx=4)

        self.btn_clear_tool_icon = ctk.CTkButton(
            r4,
            text="✕ Clear",
            width=65,
            fg_color="gray40",
            command=self._on_clear_custom_tool_icon,
        )
        self.btn_clear_tool_icon.pack(side="left", padx=(4, 16))

        ctk.CTkLabel(r4, text="Tool size").pack(side="left", padx=(0, 4))
        self.entry_tool_size = ctk.CTkEntry(r4, width=65)
        self.entry_tool_size.insert(0, "2.5")
        self.entry_tool_size.pack(side="left", padx=4)
        self.entry_tool_size.bind("<KeyRelease>", lambda e: self._on_field_change())

    def _render_dynamic_comp_inputs(self):
        """Builds input fields corresponding to the selected compartment mode."""
        for c in self.comp_inputs_frame.winfo_children():
            c.destroy()

        mode = self.fastener_cfg.compartment_mode

        if mode == "single":
            ctk.CTkLabel(self.comp_inputs_frame, text="Length:").pack(side="left", padx=(0, 4))
            self.entry_len_single = ctk.CTkEntry(self.comp_inputs_frame, width=90)
            self.entry_len_single.insert(0, self.fastener_cfg.length_single)
            self.entry_len_single.pack(side="left", padx=4)
            self.entry_len_single.bind("<KeyRelease>", lambda e: self._on_field_change())

            ctk.CTkLabel(self.comp_inputs_frame, text="Standard / Line 1:").pack(side="left", padx=(15, 4))
            self.entry_std_1 = ctk.CTkEntry(self.comp_inputs_frame, width=100)
            self.entry_std_1.insert(0, self.fastener_cfg.standard_line1)
            self.entry_std_1.pack(side="left", padx=4)
            self.entry_std_1.bind("<KeyRelease>", lambda e: self._on_field_change())

            ctk.CTkLabel(self.comp_inputs_frame, text="Grade / Line 2:").pack(side="left", padx=(15, 4))
            self.entry_std_2 = ctk.CTkEntry(self.comp_inputs_frame, width=110)
            self.entry_std_2.insert(0, self.fastener_cfg.standard_line2)
            self.entry_std_2.pack(side="left", padx=4)
            self.entry_std_2.bind("<KeyRelease>", lambda e: self._on_field_change())

        elif mode == "dual":
            ctk.CTkLabel(self.comp_inputs_frame, text="Left Bin Length:").pack(side="left", padx=(0, 4))
            self.entry_len_dual_1 = ctk.CTkEntry(self.comp_inputs_frame, width=80)
            self.entry_len_dual_1.insert(0, self.fastener_cfg.length_dual_1)
            self.entry_len_dual_1.pack(side="left", padx=4)
            self.entry_len_dual_1.bind("<KeyRelease>", lambda e: self._on_field_change())

            ctk.CTkLabel(self.comp_inputs_frame, text="Right Bin Length:").pack(side="left", padx=(15, 4))
            self.entry_len_dual_2 = ctk.CTkEntry(self.comp_inputs_frame, width=80)
            self.entry_len_dual_2.insert(0, self.fastener_cfg.length_dual_2)
            self.entry_len_dual_2.pack(side="left", padx=4)
            self.entry_len_dual_2.bind("<KeyRelease>", lambda e: self._on_field_change())

        elif mode == "quad":
            ctk.CTkLabel(self.comp_inputs_frame, text="Top-Left:").pack(side="left", padx=(0, 4))
            self.entry_len_q1 = ctk.CTkEntry(self.comp_inputs_frame, width=70)
            self.entry_len_q1.insert(0, self.fastener_cfg.length_quad_1)
            self.entry_len_q1.pack(side="left", padx=4)
            self.entry_len_q1.bind("<KeyRelease>", lambda e: self._on_field_change())

            ctk.CTkLabel(self.comp_inputs_frame, text="Top-Right:").pack(side="left", padx=(10, 4))
            self.entry_len_q2 = ctk.CTkEntry(self.comp_inputs_frame, width=70)
            self.entry_len_q2.insert(0, self.fastener_cfg.length_quad_2)
            self.entry_len_q2.pack(side="left", padx=4)
            self.entry_len_q2.bind("<KeyRelease>", lambda e: self._on_field_change())

            ctk.CTkLabel(self.comp_inputs_frame, text="Bot-Left:").pack(side="left", padx=(10, 4))
            self.entry_len_q3 = ctk.CTkEntry(self.comp_inputs_frame, width=70)
            self.entry_len_q3.insert(0, self.fastener_cfg.length_quad_3)
            self.entry_len_q3.pack(side="left", padx=4)
            self.entry_len_q3.bind("<KeyRelease>", lambda e: self._on_field_change())

            ctk.CTkLabel(self.comp_inputs_frame, text="Bot-Right:").pack(side="left", padx=(10, 4))
            self.entry_len_q4 = ctk.CTkEntry(self.comp_inputs_frame, width=70)
            self.entry_len_q4.insert(0, self.fastener_cfg.length_quad_4)
            self.entry_len_q4.pack(side="left", padx=4)
            self.entry_len_q4.bind("<KeyRelease>", lambda e: self._on_field_change())

        elif mode == "assortment":
            ctk.CTkLabel(self.comp_inputs_frame, text="Description Line 1:").pack(side="left", padx=(0, 4))
            self.entry_assort_1 = ctk.CTkEntry(self.comp_inputs_frame, width=130)
            self.entry_assort_1.insert(0, self.fastener_cfg.assortment_line1)
            self.entry_assort_1.pack(side="left", padx=4)
            self.entry_assort_1.bind("<KeyRelease>", lambda e: self._on_field_change())

            ctk.CTkLabel(self.comp_inputs_frame, text="Line 2:").pack(side="left", padx=(15, 4))
            self.entry_assort_2 = ctk.CTkEntry(self.comp_inputs_frame, width=130)
            self.entry_assort_2.insert(0, self.fastener_cfg.assortment_line2)
            self.entry_assort_2.pack(side="left", padx=4)
            self.entry_assort_2.bind("<KeyRelease>", lambda e: self._on_field_change())

    # =========================================================================
    # ARCHETYPE B FORM: DISCRETE COMPONENTS & ELECTRICAL HARDWARE
    # =========================================================================

    def _build_component_form(self):
        f = self.frame_component

        # Row 1: Category Banner, Component Icon, Bin Width
        self.r1_comp = ctk.CTkFrame(f, fg_color="transparent")
        self.r1_comp.pack(fill="x", pady=4)
        r1 = self.r1_comp

        ctk.CTkLabel(r1, text="Category", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(0, 6))
        self.entry_banner_b = ctk.CTkComboBox(
            r1,
            values=component_categories(self.language),
            width=180,
            command=lambda v: self._on_field_change(),
        )
        self.entry_banner_b.set(component_categories(self.language)[0])
        self.entry_banner_b.pack(side="left", padx=4)
        self.entry_banner_b.bind("<KeyRelease>", lambda e: self._on_field_change())

        ctk.CTkLabel(r1, text="Label length (mm)").pack(side="left", padx=(20, 6))
        self.entry_width_b = ctk.CTkEntry(r1, width=70)
        self.entry_width_b.insert(0, "38")
        self.entry_width_b.pack(side="left", padx=4)
        self.entry_width_b.bind("<KeyRelease>", lambda e: self._on_field_change())

        # Row 1b: Right Icon Frame
        r_icon = ctk.CTkFrame(f, fg_color="transparent")
        r_icon.pack(fill="x", pady=(4, 6))

        ctk.CTkLabel(r_icon, text="Icon", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(0, 8))

        self.btn_pick_comp_icon = ctk.CTkButton(
            r_icon,
            text="🖼 Choose File...",
            width=120,
            command=self._on_browse_custom_comp_icon,
        )
        self.btn_pick_comp_icon.pack(side="left", padx=(0, 6))

        self.btn_lib_comp_icon = ctk.CTkButton(
            r_icon,
            text="📚 Library...",
            width=100,
            fg_color="#0284C7",
            hover_color="#0369A1",
            command=self._on_open_comp_library,
        )
        self.btn_lib_comp_icon.pack(side="left", padx=(0, 6))

        self.lbl_custom_comp_icon = ctk.CTkLabel(
            r_icon,
            text="No icon chosen",
            text_color="gray",
        )
        self.lbl_custom_comp_icon.pack(side="left", padx=4)

        self.btn_clear_comp_icon = ctk.CTkButton(
            r_icon,
            text="✕ Clear",
            width=65,
            fg_color="gray40",
            command=self._on_clear_custom_comp_icon,
        )
        self.btn_clear_comp_icon.pack(side="left", padx=6)

        # Row 2: Primary Spec Line
        r2 = ctk.CTkFrame(f, fg_color="transparent")
        r2.pack(fill="x", pady=(10, 4))

        ctk.CTkLabel(r2, text="Part or model", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(0, 6))
        self.entry_spec_pri = ctk.CTkEntry(r2, width=280)
        self.entry_spec_pri.insert(0, "608ZZ")
        self.entry_spec_pri.pack(side="left", padx=4)
        self.entry_spec_pri.bind("<KeyRelease>", lambda e: self._on_field_change())

        # Row 3: Secondary Spec Line / Subtitle
        r3 = ctk.CTkFrame(f, fg_color="transparent")
        r3.pack(fill="x", pady=(6, 4))

        ctk.CTkLabel(r3, text="Notes").pack(side="left", padx=(0, 6))
        self.entry_spec_sec = ctk.CTkEntry(r3, width=280, placeholder_text="Optional (e.g. 0.2 - 4.0 mm² / Inline Type)")
        self.entry_spec_sec.pack(side="left", padx=4)
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

    def _on_language_changed(self, display_name: str):
        lang = next((code for code, name in LANGUAGES.items() if name == display_name), None)
        if not lang or lang == self.language:
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
        mode_map = {
            "Single Size": "single",
            "2-Bin (Dual)": "dual",
            "4-Bin (2×2 Grid)": "quad",
            "Assortment Text": "assortment",
        }
        self.fastener_cfg.compartment_mode = mode_map.get(value, "dual")
        self._render_dynamic_comp_inputs()
        self._on_field_change()

    def _on_tool_type_changed(self, value: str):
        tool_map = {
            "Socket (⬢)": "internal_hex",
            "Hex Wrench (⬡)": "external_hex",
            "Washer (◉)": "washer",
            "Torx (✶)": "torx",
            "Phillips (✚)": "phillips",
            "Slotted (-)": "slotted",
            "Custom (🖼)": "custom",
            "None": "none",
        }
    def _on_browse_custom_tool_icon(self):
        path = filedialog.askopenfilename(
            title="Select Tool Drive Icon",
            filetypes=[
                ("Image Files", "*.png;*.jpg;*.jpeg;*.bmp;*.webp;*.ico"),
                ("All Files", "*.*"),
            ],
        )
        if path:
            self._set_tool_icon_path(path)

    def _set_tool_icon_path(self, path: str):
        if path and os.path.isfile(path):
            self.fastener_cfg.custom_tool_icon_path = path
            self.fastener_cfg.tool_type = "custom"
            self.lbl_custom_tool_icon.configure(text=os.path.basename(path), text_color=("gray10", "gray90"))
            self.on_change()

    def _on_open_tool_library(self):
        IconBrowserDialog(
            self,
            on_select=self._set_tool_icon_path,
            initial_category="Fasteners",
            title_suffix="Tool Drive",
        )

    def _on_clear_custom_tool_icon(self):
        self.fastener_cfg.custom_tool_icon_path = None
        self.fastener_cfg.tool_type = "none"
        self.lbl_custom_tool_icon.configure(text="No icon chosen", text_color="gray")
        self.on_change()

    def _on_browse_custom_comp_icon(self):
        path = filedialog.askopenfilename(
            title="Select Component Icon",
            filetypes=[
                ("Image Files", "*.png;*.jpg;*.jpeg;*.bmp;*.webp;*.ico"),
                ("All Files", "*.*"),
            ],
        )
        if path:
            self._set_comp_icon_path(path)

    def _set_comp_icon_path(self, path: str):
        if path and os.path.isfile(path):
            self.component_cfg.custom_icon_path = path
            self.component_cfg.icon_type = "custom"
            self.lbl_custom_comp_icon.configure(text=os.path.basename(path), text_color=("gray10", "gray90"))
            self.on_change()

    def _on_open_comp_library(self):
        IconBrowserDialog(
            self,
            on_select=self._set_comp_icon_path,
            initial_category="Engineering",
            title_suffix="Component Icon",
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

            mode_rev = {
                "single": "Single Size",
                "dual": "2-Bin (Dual)",
                "quad": "4-Bin (2×2 Grid)",
                "assortment": "Assortment Text",
            }
            self.mode_seg.set(mode_rev.get(self.fastener_cfg.compartment_mode, "2-Bin (Dual)"))
            self._render_dynamic_comp_inputs()

            self.entry_tool_size.delete(0, "end")
            self.entry_tool_size.insert(0, self.fastener_cfg.tool_size)

            if self.fastener_cfg.custom_tool_icon_path:
                self.lbl_custom_tool_icon.configure(
                    text=os.path.basename(self.fastener_cfg.custom_tool_icon_path),
                    text_color=("gray10", "gray90"),
                )
            elif self.fastener_cfg.tool_type and self.fastener_cfg.tool_type not in ("none", "custom"):
                tool_names = {
                    "internal_hex": "Preset: Socket (⬢)",
                    "external_hex": "Preset: Hex Wrench (⬡)",
                    "washer": "Preset: Washer (◉)",
                    "torx": "Preset: Torx (✶)",
                    "phillips": "Preset: Phillips (✚)",
                    "slotted": "Preset: Slotted (-)",
                }
                self.lbl_custom_tool_icon.configure(
                    text=tool_names.get(self.fastener_cfg.tool_type, self.fastener_cfg.tool_type),
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
                    text=os.path.basename(self.component_cfg.custom_icon_path),
                    text_color=("gray10", "gray90"),
                )
            elif self.component_cfg.icon_type and self.component_cfg.icon_type not in ("none", "custom"):
                icon_names = {
                    "ball_bearing": "Preset: Ball Bearing (◎)",
                    "wago": "Preset: WAGO (⧉)",
                    "fuse": "Preset: Fuse (⊷)",
                }
                self.lbl_custom_comp_icon.configure(
                    text=icon_names.get(self.component_cfg.icon_type, self.component_cfg.icon_type),
                    text_color=("gray10", "gray90"),
                )
            else:
                self.lbl_custom_comp_icon.configure(text="No icon chosen", text_color="gray")
