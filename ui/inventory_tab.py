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
    INVENTORY_PRESETS,
)


class HardwareInventoryTab(ctk.CTkFrame):
    """Interactive editor for V2 Hardware Inventory bin labels."""

    def __init__(self, master, on_change: Callable[[], None], on_add_queue: Callable[[], None], **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)

        self.on_change = on_change
        self.on_add_queue = on_add_queue

        self.active_archetype = "fastener"  # "fastener" (Archetype A) or "component" (Archetype B)
        self.fastener_cfg = copy.deepcopy(INVENTORY_PRESETS["A2: Socket Cap 2-Bin (M3 x30 x35)"])
        self.component_cfg = copy.deepcopy(INVENTORY_PRESETS["B1: Ball Bearings (KULLAGER 608ZZ)"])

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
                self.archetype_seg.set("🔩 Threaded Fasteners (Type A)")
                self.frame_component.pack_forget()
                self.frame_fastener.pack(fill="both", expand=True, padx=12, pady=10)
            elif isinstance(cfg, ComponentLabelConfig):
                self.active_archetype = "component"
                self.component_cfg = copy.deepcopy(cfg)
                self.archetype_seg.set("⚡ Components & Electrical (Type B)")
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
        ctk.CTkLabel(top_bar, text="Archetype:", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left", padx=(0, 6))
        self.archetype_seg = ctk.CTkSegmentedButton(
            top_bar,
            values=["🔩 Threaded Fasteners (Type A)", "⚡ Components & Electrical (Type B)"],
            command=self._on_archetype_switch,
        )
        self.archetype_seg.set("🔩 Threaded Fasteners (Type A)")
        self.archetype_seg.pack(side="left", padx=4)

        # Preset Quick-Loader
        ctk.CTkLabel(top_bar, text="Catalog Presets:").pack(side="left", padx=(25, 6))
        preset_names = list(INVENTORY_PRESETS.keys())
        self.preset_combo = ctk.CTkComboBox(
            top_bar,
            values=preset_names,
            width=260,
            command=self._on_preset_selected,
        )
        self.preset_combo.set("A2: Socket Cap 2-Bin (M3 x30 x35)")
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

    def _build_fastener_form(self):
        f = self.frame_fastener

        # Row 1: Thread Size, Category, Width
        r1 = ctk.CTkFrame(f, fg_color="transparent")
        r1.pack(fill="x", pady=4)

        ctk.CTkLabel(r1, text="Thread Anchor (Solid Inverted):", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(0, 6))
        self.entry_thread = ctk.CTkComboBox(
            r1,
            values=["M2", "M2.5", "M3", "M4", "M5", "M6", "M8", "M10", "M12", "1/4\"", "#6-32"],
            width=90,
            command=lambda v: self._on_field_change(),
        )
        self.entry_thread.set("M3")
        self.entry_thread.pack(side="left", padx=4)
        self.entry_thread.bind("<KeyRelease>", lambda e: self._on_field_change())

        ctk.CTkLabel(r1, text="Category Header:").pack(side="left", padx=(20, 6))
        self.entry_cat = ctk.CTkComboBox(
            r1,
            values=["SKRUV", "MUTTER", "BRICKOR", "GÄNGSTÅNG", "SKRUV & MUTTER", "WOOD SCREW", "BOLTS"],
            width=150,
            command=lambda v: self._on_field_change(),
        )
        self.entry_cat.set("SKRUV")
        self.entry_cat.pack(side="left", padx=4)
        self.entry_cat.bind("<KeyRelease>", lambda e: self._on_field_change())

        ctk.CTkLabel(r1, text="Bin Width (mm):").pack(side="left", padx=(20, 6))
        self.entry_width_a = ctk.CTkEntry(r1, width=70)
        self.entry_width_a.insert(0, "38")
        self.entry_width_a.pack(side="left", padx=4)
        self.entry_width_a.bind("<KeyRelease>", lambda e: self._on_field_change())

        # Row 2: Compartment Mode Selector
        r2 = ctk.CTkFrame(f, fg_color="transparent")
        r2.pack(fill="x", pady=(10, 4))

        ctk.CTkLabel(r2, text="Compartment Layout:", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(0, 6))
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

        # Row 4: Tool Drive Badge
        r4 = ctk.CTkFrame(f, fg_color="transparent")
        r4.pack(fill="x", pady=(8, 4))

        ctk.CTkLabel(r4, text="Tool Drive Badge:", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(0, 6))
        self.tool_type_seg = ctk.CTkSegmentedButton(
            r4,
            values=["Socket (⬢)", "Hex Wrench (⬡)", "Washer (◉)", "Torx (✶)", "Phillips (✚)", "Slotted (-)", "Custom (🖼)", "None"],
            command=self._on_tool_type_changed,
        )
        self.tool_type_seg.set("Socket (⬢)")
        self.tool_type_seg.pack(side="left", padx=4)

        ctk.CTkLabel(r4, text="Tool Size:").pack(side="left", padx=(16, 4))
        self.entry_tool_size = ctk.CTkEntry(r4, width=65)
        self.entry_tool_size.insert(0, "2.5")
        self.entry_tool_size.pack(side="left", padx=4)
        self.entry_tool_size.bind("<KeyRelease>", lambda e: self._on_field_change())

        # Row 4b: Custom Tool Icon File Picker
        self.custom_tool_icon_frame = ctk.CTkFrame(f, fg_color="transparent")
        self.btn_pick_tool_icon = ctk.CTkButton(
            self.custom_tool_icon_frame,
            text="🖼 Choose Tool Icon...",
            width=150,
            command=self._on_browse_custom_tool_icon,
        )
        self.btn_pick_tool_icon.pack(side="left", padx=(0, 8))
        self.lbl_custom_tool_icon = ctk.CTkLabel(
            self.custom_tool_icon_frame,
            text="No icon chosen",
            text_color="gray",
        )
        self.lbl_custom_tool_icon.pack(side="left", padx=4)
        self.btn_clear_tool_icon = ctk.CTkButton(
            self.custom_tool_icon_frame,
            text="✕ Clear",
            width=65,
            fg_color="gray40",
            command=self._on_clear_custom_tool_icon,
        )
        self.btn_clear_tool_icon.pack(side="left", padx=8)

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

        ctk.CTkLabel(r1, text="Category Banner (Inverted Strip):", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(0, 6))
        self.entry_banner_b = ctk.CTkComboBox(
            r1,
            values=["KULLAGER", "WAGO", "SÄKRINGSHÅLLARE", "RELÄ", "MOTSTÅND", "KONDENSATOR", "DIOD", "CONNECTORS"],
            width=180,
            command=lambda v: self._on_field_change(),
        )
        self.entry_banner_b.set("KULLAGER")
        self.entry_banner_b.pack(side="left", padx=4)
        self.entry_banner_b.bind("<KeyRelease>", lambda e: self._on_field_change())

        ctk.CTkLabel(r1, text="Right Icon Frame:").pack(side="left", padx=(20, 6))
        self.icon_type_seg = ctk.CTkSegmentedButton(
            r1,
            values=["Ball Bearing (◎)", "WAGO (⧉)", "Fuse (⊷)", "Custom (🖼)", "None"],
            command=self._on_icon_type_changed,
        )
        self.icon_type_seg.set("Ball Bearing (◎)")
        self.icon_type_seg.pack(side="left", padx=4)

        ctk.CTkLabel(r1, text="Width (mm):").pack(side="left", padx=(20, 6))
        self.entry_width_b = ctk.CTkEntry(r1, width=70)
        self.entry_width_b.insert(0, "38")
        self.entry_width_b.pack(side="left", padx=4)
        self.entry_width_b.bind("<KeyRelease>", lambda e: self._on_field_change())

        # Row 1b: Custom Component Icon File Picker
        self.custom_comp_icon_frame = ctk.CTkFrame(f, fg_color="transparent")
        self.btn_pick_comp_icon = ctk.CTkButton(
            self.custom_comp_icon_frame,
            text="🖼 Choose Component Icon...",
            width=170,
            command=self._on_browse_custom_comp_icon,
        )
        self.btn_pick_comp_icon.pack(side="left", padx=(0, 8))
        self.lbl_custom_comp_icon = ctk.CTkLabel(
            self.custom_comp_icon_frame,
            text="No icon chosen",
            text_color="gray",
        )
        self.lbl_custom_comp_icon.pack(side="left", padx=4)
        self.btn_clear_comp_icon = ctk.CTkButton(
            self.custom_comp_icon_frame,
            text="✕ Clear",
            width=65,
            fg_color="gray40",
            command=self._on_clear_custom_comp_icon,
        )
        self.btn_clear_comp_icon.pack(side="left", padx=8)

        # Row 2: Primary Spec Line
        r2 = ctk.CTkFrame(f, fg_color="transparent")
        r2.pack(fill="x", pady=(10, 4))

        ctk.CTkLabel(r2, text="Primary Spec / Model Code:", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(0, 6))
        self.entry_spec_pri = ctk.CTkEntry(r2, width=280)
        self.entry_spec_pri.insert(0, "608ZZ")
        self.entry_spec_pri.pack(side="left", padx=4)
        self.entry_spec_pri.bind("<KeyRelease>", lambda e: self._on_field_change())

        # Row 3: Secondary Spec Line / Subtitle
        r3 = ctk.CTkFrame(f, fg_color="transparent")
        r3.pack(fill="x", pady=(6, 4))

        ctk.CTkLabel(r3, text="Secondary Notes / Subtitle:").pack(side="left", padx=(0, 6))
        self.entry_spec_sec = ctk.CTkEntry(r3, width=280, placeholder_text="Optional (e.g. 0.2 - 4.0 mm² / Inline Type)")
        self.entry_spec_sec.pack(side="left", padx=4)
        self.entry_spec_sec.bind("<KeyRelease>", lambda e: self._on_field_change())

    # =========================================================================
    # EVENT HANDLERS
    # =========================================================================

    def _on_archetype_switch(self, value: str):
        if "Fasteners" in value:
            self.active_archetype = "fastener"
            self.frame_component.pack_forget()
            self.frame_fastener.pack(fill="both", expand=True, padx=12, pady=10)
        else:
            self.active_archetype = "component"
            self.frame_fastener.pack_forget()
            self.frame_component.pack(fill="both", expand=True, padx=12, pady=10)
        self._collect_form_values()
        self.on_change()

    def _on_preset_selected(self, name: str):
        preset = INVENTORY_PRESETS.get(name)
        if not preset:
            return

        self._updating_ui = True
        try:
            if isinstance(preset, FastenerLabelConfig):
                self.active_archetype = "fastener"
                self.fastener_cfg = copy.deepcopy(preset)
                self.archetype_seg.set("🔩 Threaded Fasteners (Type A)")
                self.frame_component.pack_forget()
                self.frame_fastener.pack(fill="both", expand=True, padx=12, pady=10)
            else:
                self.active_archetype = "component"
                self.component_cfg = copy.deepcopy(preset)
                self.archetype_seg.set("⚡ Components & Electrical (Type B)")
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
        self.fastener_cfg.tool_type = tool_map.get(value, "none")
        if self.fastener_cfg.tool_type == "custom":
            self.custom_tool_icon_frame.pack(fill="x", pady=4)
        else:
            self.custom_tool_icon_frame.pack_forget()
        self._on_field_change()

    def _on_browse_custom_tool_icon(self):
        path = filedialog.askopenfilename(
            title="Select Custom Tool Drive Icon",
            filetypes=[
                ("Image Files", "*.png;*.jpg;*.jpeg;*.bmp;*.webp;*.ico"),
                ("All Files", "*.*"),
            ],
        )
        if path:
            self.fastener_cfg.custom_tool_icon_path = path
            self.lbl_custom_tool_icon.configure(text=os.path.basename(path), text_color=("gray10", "gray90"))
            self.on_change()

    def _on_clear_custom_tool_icon(self):
        self.fastener_cfg.custom_tool_icon_path = None
        self.lbl_custom_tool_icon.configure(text="No icon chosen", text_color="gray")
        self.on_change()

    def _on_icon_type_changed(self, value: str):
        icon_map = {
            "Ball Bearing (◎)": "ball_bearing",
            "WAGO (⧉)": "wago",
            "Fuse (⊷)": "fuse",
            "Custom (🖼)": "custom",
            "None": "none",
        }
        self.component_cfg.icon_type = icon_map.get(value, "none")
        if self.component_cfg.icon_type == "custom":
            self.custom_comp_icon_frame.pack(fill="x", pady=4)
        else:
            self.custom_comp_icon_frame.pack_forget()
        self._on_field_change()

    def _on_browse_custom_comp_icon(self):
        path = filedialog.askopenfilename(
            title="Select Custom Component Icon",
            filetypes=[
                ("Image Files", "*.png;*.jpg;*.jpeg;*.bmp;*.webp;*.ico"),
                ("All Files", "*.*"),
            ],
        )
        if path:
            self.component_cfg.custom_icon_path = path
            self.lbl_custom_comp_icon.configure(text=os.path.basename(path), text_color=("gray10", "gray90"))
            self.on_change()

    def _on_clear_custom_comp_icon(self):
        self.component_cfg.custom_icon_path = None
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
            self.fastener_cfg.category = self.entry_cat.get().strip() or "SKRUV"
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
            self.component_cfg.category_banner = self.entry_banner_b.get().strip() or "KULLAGER"
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

            tool_rev = {
                "internal_hex": "Socket (⬢)",
                "external_hex": "Hex Wrench (⬡)",
                "washer": "Washer (◉)",
                "torx": "Torx (✶)",
                "phillips": "Phillips (✚)",
                "slotted": "Slotted (-)",
                "custom": "Custom (🖼)",
                "none": "None",
            }
            self.tool_type_seg.set(tool_rev.get(self.fastener_cfg.tool_type, "None"))
            self.entry_tool_size.delete(0, "end")
            self.entry_tool_size.insert(0, self.fastener_cfg.tool_size)

            if self.fastener_cfg.tool_type == "custom":
                self.custom_tool_icon_frame.pack(fill="x", pady=4)
                if self.fastener_cfg.custom_tool_icon_path:
                    self.lbl_custom_tool_icon.configure(
                        text=os.path.basename(self.fastener_cfg.custom_tool_icon_path),
                        text_color=("gray10", "gray90"),
                    )
                else:
                    self.lbl_custom_tool_icon.configure(text="No icon chosen", text_color="gray")
            else:
                self.custom_tool_icon_frame.pack_forget()

        else:
            self.entry_banner_b.set(self.component_cfg.category_banner)
            self.entry_width_b.delete(0, "end")
            self.entry_width_b.insert(0, str(self.component_cfg.label_width_mm))

            icon_rev = {
                "ball_bearing": "Ball Bearing (◎)",
                "wago": "WAGO (⧉)",
                "fuse": "Fuse (⊷)",
                "custom": "Custom (🖼)",
                "none": "None",
            }
            self.icon_type_seg.set(icon_rev.get(self.component_cfg.icon_type, "None"))
            self.entry_spec_pri.delete(0, "end")
            self.entry_spec_pri.insert(0, self.component_cfg.spec_primary)
            self.entry_spec_sec.delete(0, "end")
            self.entry_spec_sec.insert(0, self.component_cfg.spec_secondary)

            if self.component_cfg.icon_type == "custom":
                self.custom_comp_icon_frame.pack(fill="x", pady=4)
                if self.component_cfg.custom_icon_path:
                    self.lbl_custom_comp_icon.configure(
                        text=os.path.basename(self.component_cfg.custom_icon_path),
                        text_color=("gray10", "gray90"),
                    )
                else:
                    self.lbl_custom_comp_icon.configure(text="No icon chosen", text_color="gray")
            else:
                self.custom_comp_icon_frame.pack_forget()
