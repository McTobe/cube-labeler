#!/usr/bin/env python3
"""
Main Application Window for Brother PT-P300BT Label Designer.
Combines interactive WYSIWYG preview, telemetry, rich formatting, and serial printing.
"""

import os
import sys
import copy
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
from PIL import Image

from core.font_manager import font_manager
from core.label_renderer import LabelRenderer, LabelConfig, LabelMetrics
from core.printer import (
    BrotherPrinter,
    MockBrotherPrinter,
    list_serial_ports,
)
from core.ptstatus import PrinterStatus
from ui.tape_preview import TapePreviewWidget
from ui.templates import (
    BUILTIN_PRESETS,
    get_preset_names,
    load_preset,
    export_config_to_json,
    import_config_from_json,
)
from ui.inventory_tab import HardwareInventoryTab

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class PrintLabelApp(ctk.CTk):
    """Modern Desktop GUI for Brother PT-P300BT Label Printer."""

    def __init__(self):
        super().__init__()

        self.title("Brother P-touch Cube (PT-P300BT) Label Studio")
        self.geometry("1150x850")
        self.minsize(980, 680)

        # Thread-safe cross-thread task queue
        self._task_queue = queue.Queue()
        self._process_task_queue()

        # Core Engine
        self.renderer = LabelRenderer()
        self.config = LabelConfig()
        self.active_printer = None
        self.is_printing = False
        self._updating_ui_from_config = False

        # Queue Management (Tape Waste Reduction)
        self.label_queue: List[LabelConfig] = []
        self._preview_mode: str = "current"  # "current" or "batch"

        # Current Rendered Artifacts
        self._current_preview: Optional[Image.Image] = None
        self._current_raster: Optional[Image.Image] = None
        self._current_raster_bytes: bytes = b""
        self._current_metrics: Optional[LabelMetrics] = None

        # Build UI (Bottom Action Bar is pinned to side=bottom first so it is never clipped)
        self._setup_header()
        self._setup_action_bar()
        self._setup_preview()
        self._setup_tabs()

        # Keyboard shortcuts
        self.bind("<Control-p>", lambda e: self._on_print_clicked())
        self.bind("<Control-P>", lambda e: self._on_print_clicked())
        self.bind("<Control-s>", lambda e: self._on_export_png())
        self.bind("<Control-Return>", lambda e: self._on_add_to_queue())
        self.bind("<Control-KP_Enter>", lambda e: self._on_add_to_queue())

        # Initialize Ports & Initial Render
        self._refresh_ports()
        self._trigger_render()

    def _post_to_main(self, callback):
        """Thread-safe dispatch of a callback to the Tkinter mainloop."""
        self._task_queue.put(callback)

    def _process_task_queue(self):
        """Periodically processes callbacks posted by worker threads."""
        try:
            while True:
                cb = self._task_queue.get_nowait()
                cb()
        except queue.Empty:
            pass
        except Exception:
            pass
        try:
            self.after(40, self._process_task_queue)
        except Exception:
            pass

    # =========================================================================
    # UI SETUP
    # =========================================================================

    def _setup_header(self):
        """Top bar: Connection, Port Selector, Virtual Mode, and Hardware Telemetry."""
        self.header_frame = ctk.CTkFrame(self, corner_radius=10)
        self.header_frame.pack(fill="x", padx=12, pady=(10, 6))

        # Title / Brand
        brand_frame = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        brand_frame.pack(side="left", padx=12, pady=8)

        self.app_title = ctk.CTkLabel(
            brand_frame,
            text="🏷 P-Touch Studio",
            font=ctk.CTkFont(size=18, weight="bold"),
        )
        self.app_title.pack(anchor="w")

        self.app_sub = ctk.CTkLabel(
            brand_frame,
            text="Brother PT-P300BT Bluetooth Label Printer",
            font=ctk.CTkFont(size=11),
            text_color="gray",
        )
        self.app_sub.pack(anchor="w")

        # Telemetry Card (Right)
        self.telemetry_frame = ctk.CTkFrame(self.header_frame, fg_color=("gray85", "gray20"))
        self.telemetry_frame.pack(side="right", padx=12, pady=6)

        self.status_badge = ctk.CTkLabel(
            self.telemetry_frame,
            text="● Disconnected",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#E63946",
        )
        self.status_badge.grid(row=0, column=0, padx=8, pady=2, sticky="w")

        self.battery_badge = ctk.CTkLabel(
            self.telemetry_frame,
            text="Battery: --",
            font=ctk.CTkFont(size=11),
            text_color="gray",
        )
        self.battery_badge.grid(row=0, column=1, padx=8, pady=2, sticky="w")

        self.tape_badge = ctk.CTkLabel(
            self.telemetry_frame,
            text="Tape: 12mm White/Black",
            font=ctk.CTkFont(size=11),
            text_color="gray",
        )
        self.tape_badge.grid(row=1, column=0, columnspan=2, padx=8, pady=2, sticky="w")

        # Port selection tracking
        self._selected_port_device = None
        self._port_label_to_device = {}
        self._port_device_to_label = {}

        # Center: Connection Controls
        conn_frame = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        conn_frame.pack(side="right", padx=10, pady=8)

        # Virtual Mode Switch (False by default so physical printer is primary)
        self.virtual_mode_var = ctk.BooleanVar(value=False)
        self.virtual_switch = ctk.CTkSwitch(
            conn_frame,
            text="Simulation Mode",
            variable=self.virtual_mode_var,
            command=self._on_virtual_mode_toggle,
            font=ctk.CTkFont(size=12),
        )
        self.virtual_switch.pack(side="left", padx=8)

        # Port Dropdown
        self.port_var = ctk.StringVar(value="Select Port")
        self.port_combo = ctk.CTkComboBox(
            conn_frame,
            variable=self.port_var,
            values=["Scanning..."],
            width=230,
            command=self._on_port_selected,
        )
        self.port_combo.pack(side="left", padx=4)

        # Refresh Ports Button
        self.btn_refresh_ports = ctk.CTkButton(
            conn_frame,
            text="Scan Ports",
            width=85,
            command=self._refresh_ports,
        )
        self.btn_refresh_ports.pack(side="left", padx=4)

        # Query Status Button
        self.btn_query_status = ctk.CTkButton(
            conn_frame,
            text="Check Status",
            width=100,
            command=self._on_query_status,
        )
        self.btn_query_status.pack(side="left", padx=4)

    def _setup_preview(self):
        """WYSIWYG Interactive Tape Canvas."""
        self.preview_widget = TapePreviewWidget(self)
        self.preview_widget.pack(side="top", fill="x", padx=12, pady=(0, 6))

    def _setup_tabs(self):
        """Editor container hosting Studio Mode Switcher, Custom Designer Tabview, and Hardware Studio."""
        self.editor_container = ctk.CTkFrame(self, fg_color="transparent")
        self.editor_container.pack(side="top", fill="both", expand=True, padx=12, pady=(0, 6))

        # Top Mode Bar: Studio Switcher & Queue Shortcut
        self.mode_bar = ctk.CTkFrame(self.editor_container, fg_color="transparent")
        self.mode_bar.pack(fill="x", pady=(0, 6))

        self.studio_mode_seg = ctk.CTkSegmentedButton(
            self.mode_bar,
            values=["🏷️ Custom Designer", "🔩 Hardware & Bins Studio"],
            command=self._on_studio_mode_changed,
            font=ctk.CTkFont(size=12, weight="bold"),
            height=32,
        )
        self.studio_mode_seg.set("🏷️ Custom Designer")
        self.studio_mode_seg.pack(side="left")

        self.btn_mode_queue = ctk.CTkButton(
            self.mode_bar,
            text="📋 Print Queue",
            width=120,
            height=32,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="gray30",
            hover_color="gray20",
            command=self._open_queue_tab,
        )
        self.btn_mode_queue.pack(side="right", padx=4)

        # Tabview for Custom Designer Mode
        self.tabview = ctk.CTkTabview(self.editor_container, command=self._on_tab_changed)
        self.tab_text = self.tabview.add("Text & Typography")
        self.tab_qr = self.tabview.add("QR & Barcode")
        self.tab_image = self.tabview.add("Images & Icons")
        self.tab_tape = self.tabview.add("Tape & Hardware")
        self.tab_templates = self.tabview.add("Templates & Presets")
        self.tab_queue = self.tabview.add("Print Queue")

        # Container for Hardware & Bins Studio Mode
        self.inventory_studio_frame = ctk.CTkFrame(self.editor_container, fg_color="transparent")
        self._build_inventory_studio()

        # Build custom tabs
        self._build_text_tab()
        self._build_qr_tab()
        self._build_image_tab()
        self._build_tape_tab()
        self._build_templates_tab()
        self._build_queue_tab()

        # Pack default view
        self.tabview.pack(fill="both", expand=True)

    # -------------------------------------------------------------------------
    # TAB 1: TEXT & TYPOGRAPHY
    # -------------------------------------------------------------------------
    def _build_text_tab(self):
        tab = self.tab_text

        # Left Column: Text editor
        left_col = ctk.CTkFrame(tab, fg_color="transparent")
        left_col.pack(side="left", fill="both", expand=True, padx=(0, 8), pady=4)

        ctk.CTkLabel(
            left_col, text="Label Text (supports multiline, \\n, or Enter):", font=ctk.CTkFont(size=12, weight="bold")
        ).pack(anchor="w", pady=(0, 2))

        self.text_editor = ctk.CTkTextbox(left_col, height=110, font=("Segoe UI", 13))
        self.text_editor.pack(fill="both", expand=True, pady=(0, 6))
        self.text_editor.insert("1.0", "HELLO WORLD\nBrother PT-P300BT")
        self.text_editor.bind("<KeyRelease>", lambda e: self._on_text_changed())
        self.text_editor.bind("<Control-Return>", lambda e: (self._on_add_to_queue(), "break")[1])
        self.text_editor.bind("<Control-KP_Enter>", lambda e: (self._on_add_to_queue(), "break")[1])

        # Alignment and Quick Action
        text_ctrl_frame = ctk.CTkFrame(left_col, fg_color="transparent")
        text_ctrl_frame.pack(fill="x")

        ctk.CTkLabel(text_ctrl_frame, text="Alignment:").pack(side="left", padx=(0, 6))
        self.align_seg = ctk.CTkSegmentedButton(
            text_ctrl_frame,
            values=["Left", "Center", "Right"],
            command=self._on_align_changed,
        )
        self.align_seg.set("Center")
        self.align_seg.pack(side="left", padx=4)

        self.btn_clear_text = ctk.CTkButton(
            text_ctrl_frame, text="Clear", width=60, fg_color="gray40", command=self._on_clear_text
        )
        self.btn_clear_text.pack(side="right", padx=4)

        # Right Column: Font & Sizing Controls
        right_col = ctk.CTkFrame(tab)
        right_col.pack(side="right", fill="both", expand=True, padx=(8, 0), pady=4)

        # Font Selection Row
        font_row = ctk.CTkFrame(right_col, fg_color="transparent")
        font_row.pack(fill="x", padx=10, pady=4)

        ctk.CTkLabel(font_row, text="Font Family:").pack(side="left", padx=(0, 6))
        available_fonts = font_manager.get_font_names()
        self.font_combo = ctk.CTkComboBox(
            font_row,
            values=available_fonts[:40],
            width=200,
            command=self._on_font_changed,
        )
        self.font_combo.set("Arial" if "Arial" in available_fonts else available_fonts[0])
        self.font_combo.pack(side="left", padx=4)

        self.btn_browse_font = ctk.CTkButton(
            font_row, text="Browse .TTF...", width=100, command=self._on_browse_font
        )
        self.btn_browse_font.pack(side="left", padx=6)

        # Sizing Row: Auto-Fit vs Fixed Size
        size_row = ctk.CTkFrame(right_col, fg_color="transparent")
        size_row.pack(fill="x", padx=10, pady=4)

        self.auto_fit_var = ctk.BooleanVar(value=True)
        self.chk_autofit = ctk.CTkCheckBox(
            size_row,
            text="Auto-Fit to Tape Height",
            variable=self.auto_fit_var,
            command=self._on_autofit_toggle,
        )
        self.chk_autofit.pack(side="left", padx=(0, 10))

        self.fixed_size_label = ctk.CTkLabel(size_row, text="Size:")
        self.fixed_size_label.pack(side="left", padx=(10, 4))
        self.fixed_size_slider = ctk.CTkSlider(
            size_row, from_=8, to=80, number_of_steps=72, width=130, command=self._on_fixed_size_slide
        )
        self.fixed_size_slider.set(36)
        self.fixed_size_slider.pack(side="left", padx=4)
        self.fixed_size_val_label = ctk.CTkLabel(size_row, text="36 pt", width=45)
        self.fixed_size_val_label.pack(side="left")

        # Font Scaling & Line Spacing
        slider_grid = ctk.CTkFrame(right_col, fg_color="transparent")
        slider_grid.pack(fill="x", padx=10, pady=4)

        # Font Scale
        ctk.CTkLabel(slider_grid, text="Font Scale:").grid(row=0, column=0, sticky="w", pady=2)
        self.scale_slider = ctk.CTkSlider(
            slider_grid, from_=50, to=150, number_of_steps=20, width=150, command=self._on_scale_slide
        )
        self.scale_slider.set(100)
        self.scale_slider.grid(row=0, column=1, padx=6, pady=2)
        self.scale_val_label = ctk.CTkLabel(slider_grid, text="100%", width=45)
        self.scale_val_label.grid(row=0, column=2, sticky="w")

        # Line Spacing
        ctk.CTkLabel(slider_grid, text="Line Spacing:").grid(row=1, column=0, sticky="w", pady=2)
        self.spacing_slider = ctk.CTkSlider(
            slider_grid, from_=0.8, to=2.0, number_of_steps=24, width=150, command=self._on_spacing_slide
        )
        self.spacing_slider.set(1.2)
        self.spacing_slider.grid(row=1, column=1, padx=6, pady=2)
        self.spacing_val_label = ctk.CTkLabel(slider_grid, text="1.2x", width=45)
        self.spacing_val_label.grid(row=1, column=2, sticky="w")

        # Padding & Outline
        ctk.CTkLabel(slider_grid, text="H-Padding:").grid(row=0, column=3, sticky="w", padx=(15, 2))
        self.padding_slider = ctk.CTkSlider(
            slider_grid, from_=0, to=40, number_of_steps=40, width=120, command=self._on_padding_slide
        )
        self.padding_slider.set(8)
        self.padding_slider.grid(row=0, column=4, padx=4)
        self.padding_val_label = ctk.CTkLabel(slider_grid, text="8 px", width=40)
        self.padding_val_label.grid(row=0, column=5)

        ctk.CTkLabel(slider_grid, text="Outline:").grid(row=1, column=3, sticky="w", padx=(15, 2))
        self.outline_slider = ctk.CTkSlider(
            slider_grid, from_=0, to=4, number_of_steps=4, width=120, command=self._on_outline_slide
        )
        self.outline_slider.set(0)
        self.outline_slider.grid(row=1, column=4, padx=4)
        self.outline_val_label = ctk.CTkLabel(slider_grid, text="0 px", width=40)
        self.outline_val_label.grid(row=1, column=5)

    # -------------------------------------------------------------------------
    # STUDIO MODE & HARDWARE BINS STUDIO
    # -------------------------------------------------------------------------
    def _open_queue_tab(self):
        """Switch to Custom Designer mode and open the Print Queue tab."""
        self.studio_mode_seg.set("🏷️ Custom Designer")
        self._on_studio_mode_changed("🏷️ Custom Designer")
        self.tabview.set("Print Queue")
        self._on_tab_changed()

    def _on_studio_mode_changed(self, mode: str):
        """Switches between Custom Designer (tabview) and Hardware & Bins Studio."""
        if mode == "🔩 Hardware & Bins Studio":
            self.tabview.pack_forget()
            self.inventory_studio_frame.pack(fill="both", expand=True)
            if hasattr(self, "design_bar_frame") and hasattr(self, "queue_bar_frame"):
                self.queue_bar_frame.pack_forget()
                self.design_bar_frame.pack(side="left")
            if hasattr(self, "inventory_tab_widget"):
                self.config.inventory_config = self.inventory_tab_widget.get_current_inventory_config()
            if self._preview_mode == "batch":
                self._preview_mode = "current"
                if hasattr(self, "btn_preview_mode"):
                    self.btn_preview_mode.configure(text="👁 Preview Chain", fg_color="#1976D2")
            self._trigger_render()
        else:
            self.inventory_studio_frame.pack_forget()
            self.tabview.pack(fill="both", expand=True)
            self._on_tab_changed()

    def _build_inventory_studio(self):
        """Constructs the dedicated Hardware Inventory Studio."""
        self.inventory_tab_widget = HardwareInventoryTab(
            self.inventory_studio_frame,
            on_change=self._on_inventory_field_changed,
            on_add_queue=self._on_add_to_queue,
        )
        self.inventory_tab_widget.pack(fill="both", expand=True)

    def _on_inventory_field_changed(self):
        """Triggered when any field in the Hardware & Bins editor changes."""
        if hasattr(self, "inventory_tab_widget"):
            self.config.inventory_config = self.inventory_tab_widget.get_current_inventory_config()
            self._trigger_render()

    # -------------------------------------------------------------------------
    # TAB 2: QR CODE & BARCODE
    # -------------------------------------------------------------------------
    def _build_qr_tab(self):
        tab = self.tab_qr

        container = ctk.CTkFrame(tab, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=12, pady=10)

        # Enable Switch
        self.qr_enable_var = ctk.BooleanVar(value=False)
        self.chk_qr_enable = ctk.CTkSwitch(
            container,
            text="Enable QR Code on Label",
            variable=self.qr_enable_var,
            command=self._on_qr_toggle,
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self.chk_qr_enable.pack(anchor="w", pady=(0, 10))

        # QR Data Entry
        ctk.CTkLabel(container, text="QR Code Payload (URL, Text, WiFi):").pack(anchor="w", pady=(4, 2))
        self.qr_data_entry = ctk.CTkEntry(
            container, placeholder_text="https://example.com or WIFI:S:MyNet;P:Secret;;", width=500
        )
        self.qr_data_entry.pack(fill="x", pady=(0, 10))
        self.qr_data_entry.insert(0, "https://github.com/Ircama/PT-P300BT")
        self.qr_data_entry.bind("<KeyRelease>", lambda e: self._on_qr_data_changed())

        # QR Settings Controls
        ctrl_row = ctk.CTkFrame(container, fg_color="transparent")
        ctrl_row.pack(fill="x", pady=6)

        ctk.CTkLabel(ctrl_row, text="Position:").pack(side="left", padx=(0, 6))
        self.qr_pos_seg = ctk.CTkSegmentedButton(
            ctrl_row,
            values=["Left of Text", "Right of Text"],
            command=self._on_qr_pos_changed,
        )
        self.qr_pos_seg.set("Left of Text")
        self.qr_pos_seg.pack(side="left", padx=4)

        ctk.CTkLabel(ctrl_row, text="QR Scale:").pack(side="left", padx=(20, 6))
        self.qr_scale_slider = ctk.CTkSlider(
            ctrl_row, from_=0.6, to=1.1, number_of_steps=10, width=150, command=self._on_qr_scale_slide
        )
        self.qr_scale_slider.set(0.95)
        self.qr_scale_slider.pack(side="left", padx=4)
        self.qr_scale_label = ctk.CTkLabel(ctrl_row, text="95%")
        self.qr_scale_label.pack(side="left", padx=4)

        # WiFi QR Helper Button
        self.btn_wifi_helper = ctk.CTkButton(
            ctrl_row,
            text="📶 Create WiFi QR",
            width=130,
            command=self._show_wifi_dialog,
        )
        self.btn_wifi_helper.pack(side="right", padx=6)

    # -------------------------------------------------------------------------
    # TAB 3: IMAGES & ICONS
    # -------------------------------------------------------------------------
    def _build_image_tab(self):
        tab = self.tab_image

        container = ctk.CTkFrame(tab, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=12, pady=10)

        # File Selection Row
        file_row = ctk.CTkFrame(container, fg_color="transparent")
        file_row.pack(fill="x", pady=(0, 10))

        self.btn_pick_img = ctk.CTkButton(
            file_row, text="🖼 Choose Image File...", width=160, command=self._on_browse_image
        )
        self.btn_pick_img.pack(side="left", padx=(0, 8))

        self.img_path_label = ctk.CTkLabel(
            file_row, text="No image selected (supports PNG, JPG, BMP)", text_color="gray"
        )
        self.img_path_label.pack(side="left", fill="x", expand=True)

        self.btn_clear_img = ctk.CTkButton(
            file_row, text="Remove", width=70, fg_color="gray40", command=self._on_clear_image
        )
        self.btn_clear_img.pack(side="right", padx=4)

        # Sliders: Position, Scale, Binarization Threshold
        img_ctrl_grid = ctk.CTkFrame(container, fg_color="transparent")
        img_ctrl_grid.pack(fill="x", pady=6)

        ctk.CTkLabel(img_ctrl_grid, text="Position:").grid(row=0, column=0, sticky="w", pady=4)
        self.img_pos_seg = ctk.CTkSegmentedButton(
            img_ctrl_grid,
            values=["Left of Text", "Right of Text"],
            command=self._on_img_pos_changed,
        )
        self.img_pos_seg.set("Left of Text")
        self.img_pos_seg.grid(row=0, column=1, sticky="w", padx=6)

        ctk.CTkLabel(img_ctrl_grid, text="Scale:").grid(row=0, column=2, sticky="w", padx=(20, 6))
        self.img_scale_slider = ctk.CTkSlider(
            img_ctrl_grid, from_=0.3, to=1.5, number_of_steps=24, width=150, command=self._on_img_scale_slide
        )
        self.img_scale_slider.set(1.0)
        self.img_scale_slider.grid(row=0, column=3, padx=4)
        self.img_scale_label = ctk.CTkLabel(img_ctrl_grid, text="100%")
        self.img_scale_label.grid(row=0, column=4, sticky="w")

        # Threshold Slider (monochrome cutoff)
        ctk.CTkLabel(img_ctrl_grid, text="Binarization Threshold:").grid(row=1, column=0, sticky="w", pady=6)
        self.threshold_slider = ctk.CTkSlider(
            img_ctrl_grid, from_=20, to=220, number_of_steps=40, width=160, command=self._on_threshold_slide
        )
        self.threshold_slider.set(100)
        self.threshold_slider.grid(row=1, column=1, padx=6)
        self.threshold_label = ctk.CTkLabel(img_ctrl_grid, text="100")
        self.threshold_label.grid(row=1, column=2, sticky="w")

    # -------------------------------------------------------------------------
    # TAB 4: TAPE & HARDWARE SETTINGS
    # -------------------------------------------------------------------------
    def _build_tape_tab(self):
        tab = self.tab_tape

        container = ctk.CTkFrame(tab, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=12, pady=10)

        row1 = ctk.CTkFrame(container, fg_color="transparent")
        row1.pack(fill="x", pady=6)

        # Tape Width
        ctk.CTkLabel(row1, text="Tape Width:").pack(side="left", padx=(0, 8))
        self.tape_width_seg = ctk.CTkSegmentedButton(
            row1,
            values=["12mm", "9mm", "6mm", "3.5mm"],
            command=self._on_tape_width_changed,
        )
        self.tape_width_seg.set("12mm")
        self.tape_width_seg.pack(side="left", padx=4)

        # Color Theme Presets
        ctk.CTkLabel(row1, text="Tape Color Scheme:").pack(side="left", padx=(30, 8))
        self.color_scheme_combo = ctk.CTkComboBox(
            row1,
            values=[
                "White Tape / Black Text",
                "Yellow Tape / Black Text",
                "Red Tape / White Text",
                "Blue Tape / White Text",
                "Green Tape / White Text",
                "Black Tape / White Text",
                "Clear Tape / Black Text",
                "Gold Tape / Black Text",
            ],
            width=210,
            command=self._on_color_scheme_changed,
        )
        self.color_scheme_combo.set("White Tape / Black Text")
        self.color_scheme_combo.pack(side="left", padx=4)

        # Geometry & Guides
        row2 = ctk.CTkFrame(container, fg_color="transparent")
        row2.pack(fill="x", pady=8)

        # Fixed Length override
        ctk.CTkLabel(row2, text="Fixed Width (mm):").pack(side="left", padx=(0, 6))
        self.fixed_width_entry = ctk.CTkEntry(row2, width=80, placeholder_text="Auto")
        self.fixed_width_entry.pack(side="left", padx=4)
        self.fixed_width_entry.bind("<KeyRelease>", lambda e: self._on_fixed_width_changed())

        # Guides & Rulers checkboxes
        self.chk_guides_var = ctk.BooleanVar(value=False)
        self.chk_guides = ctk.CTkCheckBox(
            row2, text="Print Area Guides", variable=self.chk_guides_var, command=self._on_guides_toggle
        )
        self.chk_guides.pack(side="left", padx=(30, 10))

        self.chk_rulers_var = ctk.BooleanVar(value=False)
        self.chk_rulers = ctk.CTkCheckBox(
            row2, text="Rulers (cm / in)", variable=self.chk_rulers_var, command=self._on_rulers_toggle
        )
        self.chk_rulers.pack(side="left", padx=10)

        # Row 3: Hardware Boundary Marks & Reset Settings
        row3 = ctk.CTkFrame(container, fg_color="transparent")
        row3.pack(fill="x", pady=(10, 6))

        self.chk_autocut_hw_var = ctk.BooleanVar(value=True)
        self.chk_autocut_hw = ctk.CTkCheckBox(
            row3,
            text="Hardware Boundary Marks",
            variable=self.chk_autocut_hw_var,
            command=self._on_autocut_hw_toggle,
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        self.chk_autocut_hw.pack(side="left", padx=(0, 25))

        # Reset Settings Button
        self.btn_reset_settings = ctk.CTkButton(
            row3,
            text="↺ Reset Settings to Default",
            font=ctk.CTkFont(size=12),
            height=32,
            width=200,
            fg_color="gray30",
            hover_color="gray20",
            command=self._on_reset_settings,
        )
        self.btn_reset_settings.pack(side="left", padx=10)

    # -------------------------------------------------------------------------
    # TAB 5: TEMPLATES & PRESETS
    # -------------------------------------------------------------------------
    def _build_templates_tab(self):
        tab = self.tab_templates

        container = ctk.CTkFrame(tab, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=12, pady=10)

        ctk.CTkLabel(container, text="1-Click Label Presets:", font=ctk.CTkFont(size=12, weight="bold")).pack(
            anchor="w", pady=(0, 6)
        )

        preset_grid = ctk.CTkFrame(container, fg_color="transparent")
        preset_grid.pack(fill="x", pady=(0, 12))

        presets = get_preset_names()
        for idx, name in enumerate(presets):
            btn = ctk.CTkButton(
                preset_grid,
                text=name,
                width=160,
                height=34,
                command=lambda n=name: self._apply_preset(n),
            )
            r = idx // 3
            c = idx % 3
            btn.grid(row=r, column=c, padx=6, pady=4, sticky="w")

        # Import / Export Buttons
        io_row = ctk.CTkFrame(container, fg_color="transparent")
        io_row.pack(fill="x", pady=(10, 0))

        self.btn_save_template = ctk.CTkButton(
            io_row, text="💾 Save Current Design to JSON...", command=self._on_save_template
        )
        self.btn_save_template.pack(side="left", padx=6)

        self.btn_load_template = ctk.CTkButton(
            io_row, text="📂 Open Design from JSON...", command=self._on_load_template
        )
        self.btn_load_template.pack(side="left", padx=6)

    # -------------------------------------------------------------------------
    # TAB 6: PRINT QUEUE & TAPE SAVER
    # -------------------------------------------------------------------------
    def _build_queue_tab(self):
        tab = self.tab_queue

        # Top summary card for Queue stats
        self.queue_summary_card = ctk.CTkFrame(tab, corner_radius=8)
        self.queue_summary_card.pack(fill="x", padx=10, pady=(8, 6))

        stats_box = ctk.CTkFrame(self.queue_summary_card, fg_color="transparent")
        stats_box.pack(fill="x", padx=14, pady=10)

        top_stats_row = ctk.CTkFrame(stats_box, fg_color="transparent")
        top_stats_row.pack(fill="x")

        self.queue_count_label = ctk.CTkLabel(
            top_stats_row,
            text="Queue: 0 Labels",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self.queue_count_label.pack(side="left")

        self.queue_stats_label = ctk.CTkLabel(
            top_stats_row,
            text="Total Chain Length: 0.0 mm | Est. Duration: 0.0 s",
            font=ctk.CTkFont(size=12),
            text_color="gray",
        )
        self.queue_stats_label.pack(side="left", padx=(16, 0))

        self.queue_saved_badge = ctk.CTkLabel(
            stats_box,
            text="🎉 Tape Saved: 0.0 mm (Add 2+ labels to batch & eliminate wasted lead-in tape!)",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#4CAF50",
            anchor="w",
        )
        self.queue_saved_badge.pack(fill="x", pady=(4, 0))

        # Scrollable list of queued labels
        self.queue_scroll = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        self.queue_scroll.pack(fill="both", expand=True, padx=10, pady=(0, 6))
        self.queue_scroll._parent_canvas.bind("<Configure>", lambda e: self._check_queue_scrollbar(), add="+")
        self.queue_scroll._scrollbar.grid_remove()

        self._refresh_queue_display()

    def _check_queue_scrollbar(self):
        """Dynamically shows the queue scrollbar only when items overflow the visible area."""
        try:
            self.update_idletasks()
            bbox = self.queue_scroll._parent_canvas.bbox("all")
            if bbox:
                self.queue_scroll._parent_canvas.configure(scrollregion=bbox)
                content_height = bbox[3] - bbox[1]
                canvas_height = self.queue_scroll._parent_canvas.winfo_height()
                if content_height <= canvas_height or len(self.label_queue) == 0:
                    self.queue_scroll._scrollbar.grid_remove()
                else:
                    self.queue_scroll._scrollbar.grid()
            else:
                self.queue_scroll._scrollbar.grid_remove()
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # QUEUE MANAGEMENT & BATCH HANDLERS
    # -------------------------------------------------------------------------

    def _refresh_queue_display(self):
        """Re-renders the scrollable list of queued labels and updates summary stats."""
        import tkinter
        for child in list(self.queue_scroll.winfo_children()):
            child.destroy()
        try:
            tkinter.Frame.configure(self.queue_scroll, height=1)
            self.queue_scroll._parent_canvas.yview_moveto(0)
        except Exception:
            pass

        count = len(self.label_queue)

        # Update tab label with item counter
        try:
            tab_btn = self.tabview._segmented_button._buttons_dict.get("Print Queue")
            if tab_btn:
                tab_btn.configure(text=f"Print Queue ({count})" if count > 0 else "Print Queue")
        except Exception:
            pass

        # Update mode bar queue button
        if hasattr(self, "btn_mode_queue"):
            self.btn_mode_queue.configure(
                text=f"📋 Print Queue ({count})" if count > 0 else "📋 Print Queue",
                fg_color="#1976D2" if count > 0 else "gray30",
            )

        if count == 0:
            if hasattr(self, "btn_print_batch"):
                self.btn_print_batch.configure(state="disabled", text="🖨  PRINT QUEUE (0)")
            if hasattr(self, "btn_clear_queue"):
                self.btn_clear_queue.configure(state="disabled")
            if hasattr(self, "btn_preview_mode"):
                self.btn_preview_mode.configure(state="disabled")
            self.queue_count_label.configure(text="Queue: 0 Labels")
            self.queue_stats_label.configure(text="Total Chain Length: 0.0 mm | Est. Duration: 0.0 s")
            self.queue_saved_badge.configure(
                text="🎉 Tape Saved: 0.0 mm (Add 2+ labels to batch & eliminate wasted lead-in tape!)",
                text_color="#4CAF50",
            )

            # Empty state widget
            empty_frame = ctk.CTkFrame(self.queue_scroll, fg_color="transparent")
            empty_frame.pack(fill="both", expand=True, pady=40)

            ctk.CTkLabel(
                empty_frame,
                text="📋",
                font=ctk.CTkFont(size=36),
            ).pack(pady=(10, 4))

            ctk.CTkLabel(
                empty_frame,
                text="Your Print Queue is Empty",
                font=ctk.CTkFont(size=15, weight="bold"),
            ).pack(pady=2)

            ctk.CTkLabel(
                empty_frame,
                text="Design a label in any tab, then click '➕ Add to Queue' or press Ctrl+Enter.\n"
                     "All queued labels print as one continuous strip with dotted cut lines, saving ~25mm of tape per label!",
                font=ctk.CTkFont(size=12),
                text_color="gray",
                justify="center",
            ).pack(pady=4)

            self._check_queue_scrollbar()
            return

        # Enabled batch actions
        if hasattr(self, "btn_print_batch"):
            self.btn_print_batch.configure(state="normal", text=f"🖨  PRINT QUEUE ({count})")
        if hasattr(self, "btn_clear_queue"):
            self.btn_clear_queue.configure(state="normal")
        if hasattr(self, "btn_preview_mode"):
            self.btn_preview_mode.configure(state="normal")

        # Compute batch metrics
        try:
            _, _, _, b_metrics = self.renderer.render_batch(self.label_queue)
            saved = b_metrics.tape_saved_mm
            saved_in = saved / 25.4
            self.queue_count_label.configure(text=f"Queue: {count} Labels")
            self.queue_stats_label.configure(
                text=f"Total Chain: {b_metrics.print_length_mm:.1f} mm ({b_metrics.print_length_in:.2f} in)  |  Est. Print Duration: ~{b_metrics.print_duration_sec:.1f} s"
            )
            if saved > 0:
                self.queue_saved_badge.configure(
                    text=f"🎉 Tape Saved: {saved:.1f} mm (~{saved_in:.2f} in) — avoided {count - 1} blank feed cycles!",
                    text_color="#4CAF50",
                )
            else:
                self.queue_saved_badge.configure(
                    text="Add 1 more label to start saving tape on this batch!",
                    text_color="gray",
                )
        except Exception:
            pass

        # Populate queue cards
        for idx, cfg in enumerate(self.label_queue):
            card = ctk.CTkFrame(self.queue_scroll, corner_radius=6)
            card.pack(fill="x", pady=3, padx=4)

            badge = ctk.CTkLabel(
                card,
                text=f"#{idx + 1}",
                font=ctk.CTkFont(size=13, weight="bold"),
                width=36,
            )
            badge.pack(side="left", padx=(10, 6), pady=8)

            info_col = ctk.CTkFrame(card, fg_color="transparent")
            info_col.pack(side="left", fill="both", expand=True, padx=6, pady=6)

            if getattr(cfg, "inventory_config", None) is not None:
                from core.inventory_renderer import FastenerLabelConfig
                inv = cfg.inventory_config
                if isinstance(inv, FastenerLabelConfig):
                    card_title = f"📦 {inv.thread_size} {inv.category}"
                    mode_str = inv.compartment_mode.capitalize()
                    tool_str = inv.tool_type.replace("_", " ").upper()
                    details = [
                        f"Tape: {cfg.tape_width_mm}mm",
                        f"Type: Fastener ({mode_str})",
                        f"Drive: {tool_str}",
                        f"Width: {inv.label_width_mm}mm",
                    ]
                else:
                    card_title = f"📦 {inv.category_banner}: {inv.spec_primary}"
                    icon_str = inv.icon_type.replace("_", " ").upper()
                    details = [
                        f"Tape: {cfg.tape_width_mm}mm",
                        f"Type: Component",
                        f"Icon: {icon_str}",
                        f"Width: {inv.label_width_mm}mm",
                    ]
            else:
                first_line = cfg.text.strip().splitlines()[0] if cfg.text.strip() else "[Image / QR Only]"
                if len(first_line) > 35:
                    first_line = first_line[:32] + "..."
                card_title = first_line
                details = [
                    f"Tape: {cfg.tape_width_mm}mm",
                    f"Font: {cfg.font_name}",
                ]
                if cfg.qr_enabled and cfg.qr_data:
                    details.append("QR: Yes")
                if cfg.image_path:
                    details.append("Image: Yes")
                if cfg.cut_line:
                    details.append(f"Cut: {cfg.cut_line_style.capitalize()}")

            ctk.CTkLabel(
                info_col,
                text=card_title,
                font=ctk.CTkFont(size=13, weight="bold"),
                anchor="w",
            ).pack(anchor="w")

            ctk.CTkLabel(
                info_col,
                text="  •  ".join(details),
                font=ctk.CTkFont(size=11),
                text_color="gray",
                anchor="w",
            ).pack(anchor="w")

            btn_col = ctk.CTkFrame(card, fg_color="transparent")
            btn_col.pack(side="right", padx=8, pady=6)

            ctk.CTkButton(
                btn_col,
                text="▲",
                width=30,
                height=28,
                fg_color="gray30",
                hover_color="gray20",
                state="disabled" if idx == 0 else "normal",
                command=lambda i=idx: self._on_move_queue_item(i, -1),
            ).pack(side="left", padx=2)

            ctk.CTkButton(
                btn_col,
                text="▼",
                width=30,
                height=28,
                fg_color="gray30",
                hover_color="gray20",
                state="disabled" if idx == count - 1 else "normal",
                command=lambda i=idx: self._on_move_queue_item(i, 1),
            ).pack(side="left", padx=2)

            ctk.CTkButton(
                btn_col,
                text="✏ Load",
                width=55,
                height=28,
                fg_color="#1976D2",
                hover_color="#1565C0",
                command=lambda i=idx: self._on_load_queue_item(i),
            ).pack(side="left", padx=3)

            ctk.CTkButton(
                btn_col,
                text="✕",
                width=30,
                height=28,
                fg_color="#C62828",
                hover_color="#8E0000",
                command=lambda i=idx: self._on_delete_queue_item(i),
            ).pack(side="left", padx=2)

        self._check_queue_scrollbar()

    def _on_tab_changed(self):
        """Called when switching tabs in Custom Designer."""
        selected = self.tabview.get()
        if selected == "Print Queue":
            if hasattr(self, "design_bar_frame") and hasattr(self, "queue_bar_frame"):
                self.design_bar_frame.pack_forget()
                self.queue_bar_frame.pack(side="left")
            self._refresh_queue_display()
            if self.label_queue:
                self._preview_mode = "batch"
                self._render_batch_preview()
        else:
            if hasattr(self, "design_bar_frame") and hasattr(self, "queue_bar_frame"):
                self.queue_bar_frame.pack_forget()
                self.design_bar_frame.pack(side="left")
            self.config.inventory_config = None
            if self._preview_mode == "batch":
                self._preview_mode = "current"
                if hasattr(self, "btn_preview_mode"):
                    self.btn_preview_mode.configure(text="👁 Preview Chain", fg_color="#1976D2")
            self._trigger_render()

    def _on_add_to_queue(self):
        """Adds current label configuration to the print queue."""
        cfg_copy = copy.deepcopy(self.config)

        if getattr(cfg_copy, "inventory_config", None) is not None:
            from core.inventory_renderer import FastenerLabelConfig
            inv = cfg_copy.inventory_config
            if isinstance(inv, FastenerLabelConfig):
                label_summary = f"{inv.thread_size} {inv.category}"
            else:
                label_summary = f"{inv.category_banner} {inv.spec_primary}"
            cfg_copy.text = label_summary
            first_line = label_summary
        else:
            raw_text = self.text_editor.get("1.0", "end-1c")
            if not raw_text.strip() and not self.config.image_path and not self.config.qr_data:
                self.action_status_label.configure(text="Cannot add empty label to queue.")
                return
            cfg_copy.text = raw_text
            first_line = raw_text.strip().splitlines()[0] if raw_text.strip() else "[Label]"

        self.label_queue.append(cfg_copy)
        self._refresh_queue_display()

        q_len = len(self.label_queue)
        tape_saved = 25.0 * (q_len - 1)
        if len(first_line) > 25:
            first_line = first_line[:22] + "..."

        if q_len > 1:
            msg = f"Added #{q_len} '{first_line}' to queue! 🎉 Total tape saved so far: {tape_saved:.1f} mm"
        else:
            msg = f"Added #{q_len} '{first_line}' to queue. Add more labels to eliminate wasted tape!"

        self.action_status_label.configure(text=msg)

        if self._preview_mode == "batch" or (hasattr(self, "tabview") and self.tabview.get() == "Print Queue"):
            self._render_batch_preview()

    def _render_batch_preview(self):
        """Renders the stitched multi-label chain onto WYSIWYG canvas."""
        if not self.label_queue:
            self._trigger_render()
            return

        try:
            prev_img, rast_img, r_bytes, metrics = self.renderer.render_batch(self.label_queue)
            self._current_preview = prev_img
            self._current_raster = rast_img
            self._current_raster_bytes = r_bytes
            self._current_metrics = metrics
            self.preview_widget.update_content(prev_img, rast_img, metrics)
            self.btn_preview_mode.configure(text="👁 Preview: Single", fg_color="gray40")
        except Exception as e:
            self.action_status_label.configure(text=f"Batch render error: {e}")

    def _toggle_preview_mode(self):
        """Toggles between previewing single current label and entire batch chain."""
        if self._preview_mode == "batch":
            self._preview_mode = "current"
            self.btn_preview_mode.configure(text="👁 Preview Chain", fg_color="#1976D2")
            self._trigger_render()
        else:
            if not self.label_queue:
                messagebox.showinfo("Queue Empty", "Add labels to queue first to preview the batch chain.")
                return
            self._preview_mode = "batch"
            self._render_batch_preview()

    def _on_move_queue_item(self, index: int, direction: int):
        new_idx = index + direction
        if 0 <= new_idx < len(self.label_queue):
            self.label_queue[index], self.label_queue[new_idx] = (
                self.label_queue[new_idx],
                self.label_queue[index],
            )
            self._refresh_queue_display()
            if self._preview_mode == "batch" or self.tabview.get() == "Print Queue":
                self._render_batch_preview()

    def _on_delete_queue_item(self, index: int):
        if 0 <= index < len(self.label_queue):
            del self.label_queue[index]
            self._refresh_queue_display()
            if self._preview_mode == "batch" or self.tabview.get() == "Print Queue":
                if self.label_queue:
                    self._render_batch_preview()
                else:
                    self._preview_mode = "current"
                    self.btn_preview_mode.configure(text="👁 Preview Chain", fg_color="#1976D2")
                    self._trigger_render()
            self.action_status_label.configure(text=f"Removed item from queue. Remaining: {len(self.label_queue)}")

    def _on_clear_queue(self):
        if not self.label_queue:
            return
        if messagebox.askyesno("Clear Queue", f"Remove all {len(self.label_queue)} label(s) from the print queue?"):
            self.label_queue.clear()
            self._refresh_queue_display()
            if self._preview_mode == "batch" or self.tabview.get() == "Print Queue":
                self._preview_mode = "current"
                self.btn_preview_mode.configure(text="👁 Preview Chain", fg_color="#1976D2")
                self._trigger_render()
            self.action_status_label.configure(text="Print queue cleared.")

    def _on_load_queue_item(self, index: int):
        if 0 <= index < len(self.label_queue):
            cfg = copy.deepcopy(self.label_queue[index])
            self.config = cfg
            if getattr(cfg, "inventory_config", None) is not None and hasattr(self, "inventory_tab_widget"):
                self.studio_mode_seg.set("🔩 Hardware & Bins Studio")
                self._on_studio_mode_changed("🔩 Hardware & Bins Studio")
                self.inventory_tab_widget.load_inventory_config(cfg.inventory_config)
            else:
                self.studio_mode_seg.set("🏷️ Custom Designer")
                self._on_studio_mode_changed("🏷️ Custom Designer")
                self._update_ui_from_config(cfg)
                self.tabview.set("Text & Typography")
                self._on_tab_changed()
            self._preview_mode = "current"
            self.btn_preview_mode.configure(text="👁 Preview Chain", fg_color="#1976D2")
            self._trigger_render()
            self.action_status_label.configure(text=f"Loaded queue item #{index + 1} into editor.")

    def _update_ui_from_config(self, cfg: LabelConfig):
        """Populates UI widgets from a LabelConfig object."""
        self._updating_ui_from_config = True
        try:
            self.text_editor.delete("1.0", "end")
            self.text_editor.insert("1.0", cfg.text.replace("\\n", "\n"))
            self.font_combo.set(cfg.font_name)
            self.auto_fit_var.set(cfg.auto_fit_font)
            self.fixed_size_slider.set(cfg.fixed_font_size)
            self.fixed_size_val_label.configure(text=f"{cfg.fixed_font_size} pt")
            self.scale_slider.set(int(cfg.font_scale))
            self.scale_val_label.configure(text=f"{int(cfg.font_scale)}%")
            self.outline_slider.set(cfg.stroke_width)
            self.outline_val_label.configure(text=f"{cfg.stroke_width} px")
            self.align_seg.set(cfg.alignment.capitalize())
            self.spacing_slider.set(cfg.line_spacing)
            pad = getattr(cfg, "h_padding", getattr(cfg, "h_padding_dots", 8))
            self.padding_slider.set(pad)
            self.padding_val_label.configure(text=f"{pad} px")

            self.qr_enable_var.set(cfg.qr_enabled)
            self.qr_data_entry.delete(0, "end")
            self.qr_data_entry.insert(0, cfg.qr_data or "")
            self.qr_pos_seg.set("Left of Text" if cfg.qr_position == "left" else "Right of Text")

            tw_str = f"{cfg.tape_width_mm}mm"
            if tw_str in ["12mm", "9mm", "6mm", "3.5mm"]:
                self.tape_width_seg.set(tw_str)

            self.config.tape_bg_color = cfg.tape_bg_color
            self.config.tape_fg_color = cfg.tape_fg_color

            color_scheme_names = {
                ("#FFFFFF", "#000000"): "White Tape / Black Text",
                ("#FDD835", "#000000"): "Yellow Tape / Black Text",
                ("#E53935", "#FFFFFF"): "Red Tape / White Text",
                ("#1E88E5", "#FFFFFF"): "Blue Tape / White Text",
                ("#43A047", "#FFFFFF"): "Green Tape / White Text",
                ("#212121", "#FFFFFF"): "Black Tape / White Text",
                ("#E0E0E0", "#000000"): "Clear Tape / Black Text",
                ("#D4AF37", "#000000"): "Gold Tape / Black Text",
            }
            matched_scheme = color_scheme_names.get(
                (cfg.tape_bg_color, cfg.tape_fg_color), "White Tape / Black Text"
            )
            self.color_scheme_combo.set(matched_scheme)

            if cfg.fixed_width_mm:
                self.fixed_width_entry.delete(0, "end")
                self.fixed_width_entry.insert(0, str(cfg.fixed_width_mm))
            else:
                self.fixed_width_entry.delete(0, "end")

            self.chk_guides_var.set(cfg.show_guides)
            self.chk_rulers_var.set(cfg.show_rulers)
            self.chk_autocut_hw_var.set(cfg.auto_cut_hardware)
        finally:
            self._updating_ui_from_config = False

    # =========================================================================
    # BOTTOM ACTION BAR
    # =========================================================================
    def _setup_action_bar(self):
        """Action bar with Print button, Add to Queue / Clear Queue, Preview Chain, Export, and status log."""
        self.action_frame = ctk.CTkFrame(self, corner_radius=10)
        self.action_frame.pack(side="bottom", fill="x", padx=12, pady=(0, 10))

        inner = ctk.CTkFrame(self.action_frame, fg_color="transparent")
        inner.pack(fill="x", padx=12, pady=10)

        # 1. Design Mode Bar Buttons (Packed for Text, QR, Image, Tape, Presets tabs)
        self.design_bar_frame = ctk.CTkFrame(inner, fg_color="transparent")
        self.design_bar_frame.pack(side="left")

        # Single Label Print Button
        self.btn_print = ctk.CTkButton(
            self.design_bar_frame,
            text="🖨  PRINT (Ctrl+P)",
            font=ctk.CTkFont(size=13, weight="bold"),
            height=40,
            width=160,
            fg_color="#2E7D32",
            hover_color="#1B5E20",
            command=self._on_print_clicked,
        )
        self.btn_print.pack(side="left", padx=(0, 6))

        # Add to Queue Button
        self.btn_add_queue = ctk.CTkButton(
            self.design_bar_frame,
            text="➕ Add to Queue (Ctrl+↵)",
            font=ctk.CTkFont(size=13, weight="bold"),
            height=40,
            width=190,
            fg_color="#1976D2",
            hover_color="#1565C0",
            command=self._on_add_to_queue,
        )
        self.btn_add_queue.pack(side="left", padx=4)

        # Export PNG Button
        self.btn_export = ctk.CTkButton(
            self.design_bar_frame,
            text="Export PNG",
            height=40,
            width=105,
            command=self._on_export_png,
        )
        self.btn_export.pack(side="left", padx=4)

        # 2. Queue Mode Bar Buttons (Packed when viewing Print Queue tab)
        self.queue_bar_frame = ctk.CTkFrame(inner, fg_color="transparent")

        # Print Queue Button (replaces Print)
        self.btn_print_batch = ctk.CTkButton(
            self.queue_bar_frame,
            text="🖨  PRINT QUEUE (Ctrl+P)",
            font=ctk.CTkFont(size=13, weight="bold"),
            height=40,
            width=190,
            fg_color="#2E7D32",
            hover_color="#1B5E20",
            command=self._on_print_batch_clicked,
            state="disabled",
        )
        self.btn_print_batch.pack(side="left", padx=(0, 6))

        # Clear Queue Button (replaces Add to Queue)
        self.btn_clear_queue = ctk.CTkButton(
            self.queue_bar_frame,
            text="🗑 Clear Queue",
            font=ctk.CTkFont(size=13),
            height=40,
            width=130,
            fg_color="gray35",
            hover_color="gray25",
            command=self._on_clear_queue,
            state="disabled",
        )
        self.btn_clear_queue.pack(side="left", padx=4)

        # Preview Chain Button
        self.btn_preview_mode = ctk.CTkButton(
            self.queue_bar_frame,
            text="👁 Preview Chain",
            font=ctk.CTkFont(size=13),
            height=40,
            width=135,
            fg_color="#1976D2",
            hover_color="#1565C0",
            command=self._toggle_preview_mode,
            state="disabled",
        )
        self.btn_preview_mode.pack(side="left", padx=4)

        # Export PNG (Queue Batch)
        self.btn_export_queue = ctk.CTkButton(
            self.queue_bar_frame,
            text="Export PNG",
            height=40,
            width=105,
            command=self._on_export_png,
        )
        self.btn_export_queue.pack(side="left", padx=4)

        # Progress bar and status feedback (Center/Right)
        status_box = ctk.CTkFrame(inner, fg_color="transparent")
        status_box.pack(side="right", fill="x", expand=True, padx=(12, 0))

        self.progress_bar = ctk.CTkProgressBar(status_box, height=12)
        self.progress_bar.pack(fill="x", pady=(2, 4))
        self.progress_bar.set(0.0)

        self.action_status_label = ctk.CTkLabel(
            status_box,
            text="Ready to print.",
            font=ctk.CTkFont(size=12),
            text_color="gray",
            anchor="w",
        )
        self.action_status_label.pack(fill="x")

    # =========================================================================
    # EVENT HANDLERS & RENDERING
    # =========================================================================

    def _trigger_render(self):
        """Collects current config and re-renders the label preview."""
        if self._updating_ui_from_config:
            return

        # Read text if standard text label
        if getattr(self.config, "inventory_config", None) is None:
            raw_text = self.text_editor.get("1.0", "end-1c")
            self.config.text = raw_text

        # Render with core renderer
        try:
            prev_img, rast_img, r_bytes, metrics = self.renderer.render(self.config)
            self._current_preview = prev_img
            self._current_raster = rast_img
            self._current_raster_bytes = r_bytes
            self._current_metrics = metrics

            self.preview_widget.update_content(prev_img, rast_img, metrics)
        except Exception as e:
            self.action_status_label.configure(text=f"Render error: {e}")

    def _on_text_changed(self):
        self._trigger_render()

    def _on_align_changed(self, value: str):
        self.config.alignment = value.lower()
        self._trigger_render()

    def _on_clear_text(self):
        self.text_editor.delete("1.0", "end")
        self._trigger_render()

    def _on_font_changed(self, value: str):
        self.config.font_name = value
        self._trigger_render()

    def _on_browse_font(self):
        p = filedialog.askopenfilename(
            title="Select TrueType / OpenType Font",
            filetypes=[("Font files", "*.ttf *.otf *.ttc"), ("All files", "*.*")],
        )
        if p and os.path.isfile(p):
            display_name = font_manager.register_custom_font(p)
            if display_name:
                self.font_combo.configure(values=[display_name] + font_manager.get_font_names()[:40])
                self.font_combo.set(display_name)
                self.config.font_name = display_name
                self._trigger_render()

    def _on_autofit_toggle(self):
        self.config.auto_fit_font = self.auto_fit_var.get()
        self._trigger_render()

    def _on_fixed_size_slide(self, value):
        val = int(value)
        self.fixed_size_val_label.configure(text=f"{val} pt")
        self.config.fixed_font_size = val
        if not self.config.auto_fit_font:
            self._trigger_render()

    def _on_scale_slide(self, value):
        val = int(value)
        self.scale_val_label.configure(text=f"{val}%")
        self.config.font_scale = float(val)
        self._trigger_render()

    def _on_spacing_slide(self, value):
        val = round(value, 2)
        self.spacing_val_label.configure(text=f"{val:.2f}x")
        self.config.line_spacing = val
        self._trigger_render()

    def _on_padding_slide(self, value):
        val = int(value)
        self.padding_val_label.configure(text=f"{val} px")
        self.config.h_padding = val
        self._trigger_render()

    def _on_outline_slide(self, value):
        val = int(value)
        self.outline_val_label.configure(text=f"{val} px")
        self.config.stroke_width = val
        self._trigger_render()

    def _on_qr_toggle(self):
        self.config.qr_enabled = self.qr_enable_var.get()
        self.config.qr_data = self.qr_data_entry.get()
        self._trigger_render()

    def _on_qr_data_changed(self):
        self.config.qr_data = self.qr_data_entry.get()
        if self.config.qr_enabled:
            self._trigger_render()

    def _on_qr_pos_changed(self, value: str):
        self.config.qr_position = "left" if "Left" in value else "right"
        if self.config.qr_enabled:
            self._trigger_render()

    def _on_qr_scale_slide(self, value):
        val = round(value, 2)
        self.qr_scale_label.configure(text=f"{int(val * 100)}%")
        self.config.qr_scale = val
        if self.config.qr_enabled:
            self._trigger_render()

    def _show_wifi_dialog(self):
        dialog = ctk.CTkInputDialog(text="Enter WiFi details in format: SSID,Password\n(Example: MyHomeWiFi,Secret123):", title="WiFi QR Code Generator")
        val = dialog.get_input()
        if val and "," in val:
            ssid, pwd = val.split(",", 1)
            ssid = ssid.strip()
            pwd = pwd.strip()
            wifi_code = f"WIFI:S:{ssid};T:WPA;P:{pwd};;"
            self.qr_data_entry.delete(0, "end")
            self.qr_data_entry.insert(0, wifi_code)
            self.qr_enable_var.set(True)
            self.config.qr_enabled = True
            self.config.qr_data = wifi_code
            self._trigger_render()

    def _on_browse_image(self):
        p = filedialog.askopenfilename(
            title="Select Image File",
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.bmp *.ico"), ("All files", "*.*")],
        )
        if p and os.path.isfile(p):
            self.config.image_path = p
            self.img_path_label.configure(text=os.path.basename(p))
            self._trigger_render()

    def _on_clear_image(self):
        self.config.image_path = None
        self.img_path_label.configure(text="No image selected")
        self._trigger_render()

    def _on_img_pos_changed(self, value: str):
        self.config.image_position = "left" if "Left" in value else "right"
        if self.config.image_path:
            self._trigger_render()

    def _on_img_scale_slide(self, value):
        val = round(value, 2)
        self.img_scale_label.configure(text=f"{int(val * 100)}%")
        self.config.image_scale = val
        if self.config.image_path:
            self._trigger_render()

    def _on_threshold_slide(self, value):
        val = int(value)
        self.threshold_label.configure(text=str(val))
        self.config.threshold = val
        self._trigger_render()

    def _on_tape_width_changed(self, value: str):
        num = float(value.replace("mm", ""))
        self.config.tape_width_mm = int(num)
        self._trigger_render()

    def _on_color_scheme_changed(self, value: str):
        color_map = {
            "White Tape / Black Text": ("#FFFFFF", "#000000"),
            "Yellow Tape / Black Text": ("#FDD835", "#000000"),
            "Red Tape / White Text": ("#E53935", "#FFFFFF"),
            "Blue Tape / White Text": ("#1E88E5", "#FFFFFF"),
            "Green Tape / White Text": ("#43A047", "#FFFFFF"),
            "Black Tape / White Text": ("#212121", "#FFFFFF"),
            "Clear Tape / Black Text": ("#E8F4F8", "#000000"),
            "Gold Tape / Black Text": ("#D4AF37", "#000000"),
        }
        if value in color_map:
            bg, fg = color_map[value]
            self.config.tape_bg_color = bg
            self.config.tape_fg_color = fg
            self._trigger_render()

    def _on_fixed_width_changed(self):
        val = self.fixed_width_entry.get().strip()
        try:
            self.config.fixed_width_mm = float(val) if val else None
        except ValueError:
            self.config.fixed_width_mm = None
        self._trigger_render()

    def _on_guides_toggle(self):
        self.config.show_guides = self.chk_guides_var.get()
        self._trigger_render()

    def _on_rulers_toggle(self):
        self.config.show_rulers = self.chk_rulers_var.get()
        self._trigger_render()

    def _on_reset_settings(self):
        """Resets all configuration settings back to defaults."""
        cur_text = self.text_editor.get("1.0", "end-1c")
        self.config = LabelConfig(
            text=cur_text,
            auto_cut_hardware=True,
            cut_line=False,
        )
        self._update_ui_from_config(self.config)
        self._trigger_render()
        self.action_status_label.configure(text="Settings reset to defaults.")

    def _on_autocut_hw_toggle(self):
        self.config.auto_cut_hardware = self.chk_autocut_hw_var.get()

    # -------------------------------------------------------------------------
    # TEMPLATES & PRESETS
    # -------------------------------------------------------------------------
    def _apply_preset(self, name: str):
        preset = load_preset(name)
        if not preset:
            return

        self._updating_ui_from_config = True
        try:
            # Populate text
            self.text_editor.delete("1.0", "end")
            self.text_editor.insert("1.0", preset.get("text", "").replace("\\n", "\n"))

            # Populate font
            fname = preset.get("font_name", "Arial")
            self.font_combo.set(fname)
            self.config.font_name = fname

            # Alignment
            al = preset.get("alignment", "center").capitalize()
            self.align_seg.set(al)
            self.config.alignment = al.lower()

            # Line Spacing
            sp = preset.get("line_spacing", 1.2)
            self.spacing_slider.set(sp)
            self.spacing_val_label.configure(text=f"{sp:.2f}x")
            self.config.line_spacing = sp

            # QR Code
            qr_en = preset.get("qr_enabled", False)
            self.qr_enable_var.set(qr_en)
            self.config.qr_enabled = qr_en
            if qr_en:
                qr_d = preset.get("qr_data", "")
                self.qr_data_entry.delete(0, "end")
                self.qr_data_entry.insert(0, qr_d)
                self.config.qr_data = qr_d
                self.config.qr_position = preset.get("qr_position", "left")

            # Color scheme
            bg = preset.get("tape_bg_color", "#FFFFFF")
            fg = preset.get("tape_fg_color", "#000000")
            self.config.tape_bg_color = bg
            self.config.tape_fg_color = fg
        finally:
            self._updating_ui_from_config = False

        self._trigger_render()

    def _on_save_template(self):
        p = filedialog.asksaveasfilename(
            title="Save Label Template",
            defaultextension=".json",
            filetypes=[("JSON Files", "*.json")],
        )
        if p:
            if export_config_to_json(self.config, p):
                messagebox.showinfo("Success", f"Template saved to:\n{p}")
            else:
                messagebox.showerror("Error", "Failed to save template.")

    def _on_load_template(self):
        p = filedialog.askopenfilename(
            title="Open Label Template",
            filetypes=[("JSON Files", "*.json")],
        )
        if p and os.path.isfile(p):
            cfg = import_config_from_json(p)
            if cfg:
                self.config = cfg
                self._update_ui_from_config(cfg)
                self._trigger_render()
                messagebox.showinfo("Success", "Template loaded successfully.")

    # =========================================================================
    # PORT MANAGEMENT & TELEMETRY
    # =========================================================================

    def _refresh_ports(self):
        """Scans for available serial ports, prioritizing Brother Outgoing ports."""
        ports = list_serial_ports()
        prev_device = getattr(self, "_selected_port_device", None)

        self._port_label_to_device = {p.label: p.device for p in ports}
        self._port_device_to_label = {p.device: p.label for p in ports}

        labels = [p.label for p in ports]
        if not labels:
            labels = ["No Ports Found"]
            self.port_combo.configure(values=labels)
            self.port_combo.set("No Ports Found")
            self.port_var.set("No Ports Found")
            self._selected_port_device = None
            self.virtual_mode_var.set(True)
            self._on_virtual_mode_toggle()
        else:
            self.port_combo.configure(values=labels)

            # Determine best port to select:
            target_device = None
            # 1. If previous selection is still present and valid, KEEP IT!
            if prev_device and prev_device in self._port_device_to_label:
                target_device = prev_device
            else:
                # 2. Prefer Brother Outgoing printer port (is_preferred=True)
                for p in ports:
                    if p.is_preferred:
                        target_device = p.device
                        break
                # 3. If none preferred, take first non-incoming port
                if not target_device:
                    for p in ports:
                        if not p.is_incoming:
                            target_device = p.device
                            break
                # 4. Fallback to first available port
                if not target_device:
                    target_device = ports[0].device

            target_label = self._port_device_to_label[target_device]
            self.port_combo.set(target_label)
            self.port_var.set(target_label)
            self._selected_port_device = target_device
            self.action_status_label.configure(text=f"Selected Port: {target_label}")

            # Auto-query status if physical mode
            if not self.virtual_mode_var.get():
                self._on_query_status()

    def _on_port_selected(self, value: str):
        if value and value != "No Ports Found":
            if value in self._port_label_to_device:
                self._selected_port_device = self._port_label_to_device[value]
            else:
                self._selected_port_device = value.split()[0]
            self.action_status_label.configure(text=f"Selected Port: {value}")
            if not self.virtual_mode_var.get():
                self._on_query_status()

    def _on_virtual_mode_toggle(self):
        is_virt = self.virtual_mode_var.get()
        if is_virt:
            self.status_badge.configure(text="● Simulation Mode", text_color="#00B0FF")
            self.action_status_label.configure(text="Operating in Virtual Simulation Mode.")
        else:
            self.status_badge.configure(text="● Connecting...", text_color="#FDD835")
            self.action_status_label.configure(text="Physical Mode: Connecting to printer...")
            self._on_query_status()

    def _on_query_status(self):
        """Asynchronously queries printer hardware status."""
        self.action_status_label.configure(text="Querying printer status...")

        is_virt = self.virtual_mode_var.get()
        port = getattr(self, "_selected_port_device", None)
        if not port and not is_virt:
            cur_val = self.port_var.get()
            if cur_val and cur_val != "No Ports Found":
                port = cur_val.split()[0]

        def _worker(virt_mode=is_virt, port_name=port):
            try:
                if virt_mode:
                    printer = MockBrotherPrinter()
                    status = printer.get_status()
                else:
                    if not port_name or port_name == "No Ports Found":
                        raise RuntimeError("Please select a valid COM port from the dropdown.")
                    printer = BrotherPrinter(port_name)
                    status = printer.get_status()

                self._post_to_main(lambda s=status: self._apply_telemetry(s))
            except Exception as e:
                err_msg = str(e)
                self._post_to_main(lambda m=err_msg: self._handle_query_error(m))

        threading.Thread(target=_worker, daemon=True).start()

    def _apply_telemetry(self, status: PrinterStatus):
        color = "#2E7D32" if status.is_ready else "#E63946"
        stat_text = "● Ready" if status.is_ready else f"● {status.phase_name}"
        self.status_badge.configure(text=stat_text, text_color=color)

        self.battery_badge.configure(text=f"Power: {status.power_status}")
        self.tape_badge.configure(
            text=f"Tape: {status.tape_width_mm}mm ({status.bg_color_name}/{status.fg_color_name})"
        )

        # Update tape width selector if matched
        tw_str = f"{status.tape_width_mm}mm"
        if tw_str in ["12mm", "9mm", "6mm", "3.5mm"]:
            self.tape_width_seg.set(tw_str)
            self.config.tape_width_mm = status.tape_width_mm

        # Update colors
        self.config.tape_bg_color = status.bg_color_hex
        self.config.tape_fg_color = status.fg_color_hex
        self._trigger_render()

        self.action_status_label.configure(text=f"Connected to {status.model_name}. Status: Ready.")

    def _handle_query_error(self, err: str):
        self.status_badge.configure(text="● Query Failed", text_color="#E63946")
        self.action_status_label.configure(text=f"Status check failed: {err}")

    # =========================================================================
    # PRINT EXECUTION & EXPORT
    # =========================================================================

    def _on_export_png(self):
        if not self._current_preview:
            return
        p = filedialog.asksaveasfilename(
            title="Export Label PNG",
            defaultextension=".png",
            filetypes=[("PNG Image", "*.png")],
        )
        if p:
            try:
                self._current_preview.save(p)
                self.action_status_label.configure(text=f"Exported PNG to {os.path.basename(p)}")
            except Exception as e:
                messagebox.showerror("Export Failed", str(e))

    def _on_print_clicked(self):
        # If in batch preview mode or on the Print Queue tab, print batch
        if self._preview_mode == "batch" or (hasattr(self, "tabview") and self.tabview.get() == "Print Queue"):
            if self.label_queue:
                self._on_print_batch_clicked()
                return

        if self.is_printing:
            return

        if not self._current_raster_bytes:
            messagebox.showwarning("Warning", "No label data to print.")
            return

        self.is_printing = True
        self.btn_print.configure(state="disabled")
        if hasattr(self, "btn_add_queue"):
            self.btn_add_queue.configure(state="disabled")
        if hasattr(self, "btn_feed_tape"):
            self.btn_feed_tape.configure(state="disabled")
        if hasattr(self, "btn_print_batch"):
            self.btn_print_batch.configure(state="disabled")
        self.progress_bar.set(0.0)

        is_virt = self.virtual_mode_var.get()
        port = getattr(self, "_selected_port_device", None)
        if not port and not is_virt:
            cur_val = self.port_var.get()
            if cur_val and cur_val != "No Ports Found":
                port = cur_val.split()[0]

        auto_cut = self.config.auto_cut_hardware
        data = self._current_raster_bytes

        def _print_worker(virt_mode=is_virt, port_name=port, do_cut=auto_cut, raster=data):
            try:
                if virt_mode:
                    printer = MockBrotherPrinter()
                else:
                    if not port_name or port_name == "No Ports Found":
                        raise RuntimeError("No serial COM port selected. Check Bluetooth pairing.")
                    printer = BrotherPrinter(port_name)

                def _prog(cur, total):
                    pct = cur / total
                    self._post_to_main(lambda p=pct, c=cur, t=total: self._update_progress(p, f"Sending data: {c}/{t} lines..."))

                def _stat(msg):
                    self._post_to_main(lambda m=msg: self.action_status_label.configure(text=m))

                final_status = printer.print_raster_data(
                    raster,
                    auto_cut=do_cut,
                    progress_callback=_prog,
                    status_callback=_stat,
                )
                self._post_to_main(lambda s=final_status: self._print_success(s))
            except Exception as e:
                err_msg = str(e)
                self._post_to_main(lambda m=err_msg: self._print_failure(m))

        threading.Thread(target=_print_worker, daemon=True).start()

    def _update_progress(self, pct: float, msg: str):
        self.progress_bar.set(pct)
        self.action_status_label.configure(text=msg)

    def _print_success(self, status: PrinterStatus):
        self.is_printing = False
        self.btn_print.configure(state="normal")
        if hasattr(self, "btn_add_queue"):
            self.btn_add_queue.configure(state="normal")
        has_q = bool(self.label_queue)
        if hasattr(self, "btn_print_batch"):
            self.btn_print_batch.configure(state="normal" if has_q else "disabled")
        if hasattr(self, "btn_clear_queue"):
            self.btn_clear_queue.configure(state="normal" if has_q else "disabled")
        if hasattr(self, "btn_preview_mode"):
            self.btn_preview_mode.configure(state="normal" if has_q else "disabled")
        self.progress_bar.set(1.0)
        self.action_status_label.configure(text="Print job completed successfully!")

    def _print_failure(self, err_msg: str):
        self.is_printing = False
        self.btn_print.configure(state="normal")
        if hasattr(self, "btn_add_queue"):
            self.btn_add_queue.configure(state="normal")
        has_q = bool(self.label_queue)
        if hasattr(self, "btn_print_batch"):
            self.btn_print_batch.configure(state="normal" if has_q else "disabled")
        if hasattr(self, "btn_clear_queue"):
            self.btn_clear_queue.configure(state="normal" if has_q else "disabled")
        if hasattr(self, "btn_preview_mode"):
            self.btn_preview_mode.configure(state="normal" if has_q else "disabled")
        self.progress_bar.set(0.0)
        self.action_status_label.configure(text=f"Print failed: {err_msg}")
        messagebox.showerror("Printing Error", err_msg)

    def _on_print_batch_clicked(self):
        """Prints the entire queued list of labels as one continuous strip."""
        if not self.label_queue:
            messagebox.showinfo("Queue Empty", "Please add at least one label to the queue before printing.")
            return

        if self.is_printing:
            return

        self.is_printing = True
        self.btn_print.configure(state="disabled")
        if hasattr(self, "btn_add_queue"):
            self.btn_add_queue.configure(state="disabled")
        if hasattr(self, "btn_print_batch"):
            self.btn_print_batch.configure(state="disabled")
        if hasattr(self, "btn_clear_queue"):
            self.btn_clear_queue.configure(state="disabled")
        if hasattr(self, "btn_preview_mode"):
            self.btn_preview_mode.configure(state="disabled")
        self.progress_bar.set(0.0)

        is_virt = self.virtual_mode_var.get()
        port = getattr(self, "_selected_port_device", None)
        if not port and not is_virt:
            cur_val = self.port_var.get()
            if cur_val and cur_val != "No Ports Found":
                port = cur_val.split()[0]

        try:
            prev_img, rast_img, r_bytes, metrics = self.renderer.render_batch(self.label_queue)
        except Exception as e:
            self.is_printing = False
            self.btn_print.configure(state="normal")
            if hasattr(self, "btn_add_queue"):
                self.btn_add_queue.configure(state="normal")
            has_q = bool(self.label_queue)
            if hasattr(self, "btn_print_batch"):
                self.btn_print_batch.configure(state="normal" if has_q else "disabled")
            if hasattr(self, "btn_clear_queue"):
                self.btn_clear_queue.configure(state="normal" if has_q else "disabled")
            if hasattr(self, "btn_preview_mode"):
                self.btn_preview_mode.configure(state="normal" if has_q else "disabled")
            messagebox.showerror("Render Error", f"Failed to generate batch raster data: {e}")
            return

        auto_cut = self.label_queue[-1].auto_cut_hardware
        label_count = len(self.label_queue)
        tape_saved_mm = metrics.tape_saved_mm

        def _batch_print_worker(virt_mode=is_virt, port_name=port, do_cut=auto_cut, raster=r_bytes, count=label_count, saved=tape_saved_mm):
            try:
                if virt_mode:
                    printer = MockBrotherPrinter()
                else:
                    if not port_name or port_name == "No Ports Found":
                        raise RuntimeError("No serial COM port selected. Check Bluetooth pairing.")
                    printer = BrotherPrinter(port_name)

                def _prog(cur, total):
                    pct = cur / total
                    self._post_to_main(lambda p=pct, c=cur, t=total: self._update_progress(p, f"Printing batch ({count} labels): {c}/{t} lines..."))

                def _stat(msg):
                    self._post_to_main(lambda m=msg: self.action_status_label.configure(text=m))

                final_status = printer.print_raster_data(
                    raster,
                    auto_cut=do_cut,
                    progress_callback=_prog,
                    status_callback=_stat,
                )
                self._post_to_main(lambda s=final_status, c=count, sv=saved: self._batch_print_success(s, c, sv))
            except Exception as e:
                err_msg = str(e)
                self._post_to_main(lambda m=err_msg: self._print_failure(m))

        threading.Thread(target=_batch_print_worker, daemon=True).start()

    def _batch_print_success(self, status: PrinterStatus, count: int, tape_saved: float):
        self.is_printing = False
        self.btn_print.configure(state="normal")
        if hasattr(self, "btn_add_queue"):
            self.btn_add_queue.configure(state="normal")
        self.progress_bar.set(1.0)

        success_msg = f"🎉 Batch printed {count} labels successfully! Eliminated {tape_saved:.1f} mm of wasted tape."
        self.action_status_label.configure(text=success_msg)

        if messagebox.askyesno(
            "Batch Print Complete",
            f"Successfully printed batch of {count} labels!\n\n"
            f"Eliminated {tape_saved:.1f} mm (~{tape_saved/25.4:.2f} in) of wasted tape.\n\n"
            "Would you like to clear the print queue now?"
        ):
            self.label_queue.clear()
            self._refresh_queue_display()
            self._preview_mode = "current"
            self._trigger_render()
        else:
            has_q = bool(self.label_queue)
            if hasattr(self, "btn_print_batch"):
                self.btn_print_batch.configure(state="normal" if has_q else "disabled")
            if hasattr(self, "btn_clear_queue"):
                self.btn_clear_queue.configure(state="normal" if has_q else "disabled")
            if hasattr(self, "btn_preview_mode"):
                self.btn_preview_mode.configure(state="normal" if has_q else "disabled")


def main():
    app = PrintLabelApp()
    app.mainloop()


if __name__ == "__main__":
    main()
