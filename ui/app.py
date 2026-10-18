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
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Callable, List, Optional
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
from core.config import config_manager
from core.specs import (
    INVENTORY_TAPE_WIDTH_MM,
    TAPE_LEAD_MM,
    TAPE_SPECS,
    format_tape_width,
    tape_width_from_status,
)

from core.label_language import LANGUAGES
from ui.tape_preview import TapePreviewWidget
from ui.templates import (
    load_preset,
    export_config_to_json,
    load_config_from_json,
)
from ui.inventory_tab import HardwareInventoryTab
from ui.icon_browser import IconBrowserDialog
from ui.ai_generator_dialog import AIGeneratorDialog
from ui.printer_chip import PrinterChip, PrinterPanel
from ui.settings_view import SettingsView
from ui.templates_view import TemplatesView
from ui.widgets import ACCENT, ACCENT_HOVER, MUTED_TEXT, Section, Sidebar, field_label, labeled_slider

TAPE_WIDTH_OPTIONS = [format_tape_width(w) for w in TAPE_SPECS]
FEED_LENGTH_MM = 25.0

# Views in the left rail
VIEW_TEXT = "text"
VIEW_BIN = "bin"
VIEW_QUEUE = "queue"
VIEW_TEMPLATES = "templates"
VIEW_SETTINGS = "settings"

POS_LEFT = "Left of text"
POS_RIGHT = "Right of text"

QUEUE_EMPTY_HINT = "Labels in the queue print as one strip, saving about 25 mm of tape per extra label."
QUEUE_THUMB_HEIGHT = 30
QUEUE_THUMB_MAX_WIDTH = 220

# Preview colours for common tapes: name -> (tape colour, ink colour)
COLOR_SCHEMES = {
    "White Tape / Black Text": ("#FFFFFF", "#000000"),
    "Yellow Tape / Black Text": ("#FDD835", "#000000"),
    "Red Tape / White Text": ("#E53935", "#FFFFFF"),
    "Blue Tape / White Text": ("#1E88E5", "#FFFFFF"),
    "Green Tape / White Text": ("#43A047", "#FFFFFF"),
    "Black Tape / White Text": ("#212121", "#FFFFFF"),
    "Clear Tape / Black Text": ("#E8F4F8", "#000000"),
    "Gold Tape / Black Text": ("#D4AF37", "#000000"),
}

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class PrintLabelApp(ctk.CTk):
    """Modern Desktop GUI for Brother PT-P300BT Label Printer."""

    def __init__(self):
        super().__init__()

        self.title("Brother P-touch Cube (PT-P300BT) Label Studio")
        self.geometry("1150x850")
        self.minsize(980, 680)

        # Set Window Icon
        base_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        ico_candidate = os.path.join(base_dir, "assets", "icon.ico")
        if os.path.isfile(ico_candidate):
            try:
                self.iconbitmap(ico_candidate)
            except Exception:
                pass

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
        self._view: Optional[str] = None

        # Current Rendered Artifacts
        self._current_preview: Optional[Image.Image] = None
        self._current_raster: Optional[Image.Image] = None
        self._current_raster_bytes: bytes = b""
        self._current_metrics: Optional[LabelMetrics] = None

        # Build UI (Bottom Action Bar is pinned to side=bottom first so it is never clipped)
        self._setup_header()
        self._setup_action_bar()
        self._setup_body()

        # Keyboard shortcuts
        self.bind("<Control-p>", lambda e: self._on_print_clicked())
        self.bind("<Control-P>", lambda e: self._on_print_clicked())
        self.bind("<Control-s>", lambda e: self._on_export_png())
        self.bind("<Control-Return>", lambda e: self._on_add_to_queue())
        self.bind("<Control-KP_Enter>", lambda e: self._on_add_to_queue())

        # Initialize Ports & Initial Render
        self._show_view(VIEW_TEXT)
        self._refresh_ports()

    def _post_to_main(self, callback):
        """Thread-safe dispatch of a callback to the Tkinter mainloop."""
        self._task_queue.put(callback)

    def _process_task_queue(self):
        """Periodically processes callbacks posted by worker threads."""
        while True:
            try:
                cb = self._task_queue.get_nowait()
            except queue.Empty:
                break
            try:
                cb()
            except Exception:
                # Keep processing later callbacks; never let one failure stall the UI silently.
                # sys.stderr is None in the windowed .exe build.
                if sys.stderr:
                    traceback.print_exc()
        try:
            self.after(40, self._process_task_queue)
        except Exception:
            pass

    # =========================================================================
    # LAYOUT: header with printer chip, left rail, main area, settings panel
    # =========================================================================

    def _setup_header(self):
        """Slim top bar: app name on the left, printer chip on the right."""
        self.header_frame = ctk.CTkFrame(self, corner_radius=10)
        self.header_frame.pack(fill="x", padx=12, pady=(10, 6))

        self.app_title = ctk.CTkLabel(
            self.header_frame,
            text="P-Touch Studio",
            font=ctk.CTkFont(size=17, weight="bold"),
        )
        self.app_title.pack(side="left", padx=14, pady=8)

        # Connection state shared by the printer panel, the settings view and the print code
        self.virtual_mode_var = ctk.BooleanVar(value=False)
        self.port_var = ctk.StringVar(value="Select port")
        self._selected_port_device = None
        self._port_label_to_device = {}
        self._port_device_to_label = {}

        self.printer_chip = PrinterChip(self.header_frame, command=self._toggle_printer_panel)
        self.printer_chip.pack(side="right", padx=12, pady=8)

        self.printer_panel = PrinterPanel(
            self,
            port_var=self.port_var,
            virtual_var=self.virtual_mode_var,
            on_port_selected=self._on_port_selected,
            on_scan=self._refresh_ports,
            on_check=self._on_query_status,
            on_virtual_toggle=self._on_virtual_mode_toggle,
        )
        self.port_combo = self.printer_panel.port_combo
        self.bind("<Escape>", lambda e: self._hide_printer_panel())

    def _toggle_printer_panel(self):
        if self.printer_panel.winfo_ismapped():
            self._hide_printer_panel()
        else:
            self.printer_panel.place(relx=1.0, x=-24, y=60, anchor="ne")
            self.printer_panel.lift()

    def _hide_printer_panel(self):
        self.printer_panel.place_forget()

    def _setup_body(self):
        """Left rail, main area (preview + current view) and the text label settings panel."""
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.pack(fill="both", expand=True, padx=12, pady=(0, 6))
        self.body.grid_rowconfigure(0, weight=1)
        self.body.grid_columnconfigure(1, weight=1)

        self.sidebar = Sidebar(
            self.body,
            items=[
                (VIEW_TEXT, "Text label"),
                (VIEW_BIN, "Bin label"),
                (VIEW_QUEUE, "Queue"),
                (VIEW_TEMPLATES, "Templates"),
            ],
            bottom_items=[(VIEW_SETTINGS, "Settings")],
            on_select=self._show_view,
        )
        self.sidebar.grid(row=0, column=0, sticky="ns", padx=(0, 10))

        self.main_area = ctk.CTkFrame(self.body, fg_color="transparent")
        self.main_area.grid(row=0, column=1, sticky="nsew")

        self.preview_widget = TapePreviewWidget(self.main_area)

        self.text_workspace = ctk.CTkFrame(self.main_area, fg_color="transparent")
        self._build_text_editor(self.text_workspace)

        self.inventory_studio_frame = ctk.CTkFrame(self.main_area, fg_color="transparent")
        self._build_inventory_studio()

        self.queue_container_frame = ctk.CTkFrame(self.main_area, fg_color="transparent")
        self._build_queue_view()

        self.templates_view = TemplatesView(
            self.main_area,
            on_apply=self._apply_preset_and_edit,
            on_save=self._on_save_template,
            on_open=self._on_load_template,
        )
        self.settings_view = SettingsView(
            self.main_area,
            virtual_var=self.virtual_mode_var,
            on_virtual_toggle=self._on_virtual_mode_toggle,
            on_language_changed=self._on_label_language_changed,
            on_status=lambda msg: self.action_status_label.configure(text=msg),
        )

        self.designer_panel = ctk.CTkScrollableFrame(self.body, width=300, corner_radius=10)
        self._build_designer_panel(self.designer_panel)

    # -------------------------------------------------------------------------
    # VIEW SWITCHING
    # -------------------------------------------------------------------------
    def _show_view(self, view: str):
        """Shows one of the rail's views: text, bin, queue, templates or settings."""
        self._hide_printer_panel()
        for widget in (
            self.preview_widget,
            self.text_workspace,
            self.inventory_studio_frame,
            self.queue_container_frame,
            self.templates_view,
            self.settings_view,
        ):
            widget.pack_forget()
        self.designer_panel.grid_forget()

        self._view = view
        self.sidebar.set_active(view)

        if view in (VIEW_TEXT, VIEW_BIN):
            self.preview_widget.pack(fill="both", expand=True, pady=(0, 8))
        elif view == VIEW_QUEUE:
            self.preview_widget.pack(fill="x", pady=(0, 8))

        if view == VIEW_TEXT:
            self.text_workspace.pack(fill="x")
            self.designer_panel.grid(row=0, column=2, sticky="ns", padx=(10, 0))
            self.config.inventory_config = None
        elif view == VIEW_BIN:
            self.inventory_studio_frame.pack(fill="x")
            self.config.inventory_config = self.inventory_tab_widget.get_current_inventory_config()
        elif view == VIEW_QUEUE:
            self.queue_container_frame.pack(fill="both", expand=True)
            self._refresh_queue_display()
        elif view == VIEW_TEMPLATES:
            self.templates_view.pack(fill="both", expand=True)
        elif view == VIEW_SETTINGS:
            self.settings_view.pack(fill="both", expand=True)

        self._update_action_bar()
        self._trigger_render()

    def _show_custom_designer(self):
        self._show_view(VIEW_TEXT)

    def _show_hardware_studio(self):
        self._show_view(VIEW_BIN)

    def _show_queue_view(self):
        self._show_view(VIEW_QUEUE)

    def _open_queue_tab(self):
        self._show_view(VIEW_QUEUE)

    def _is_queue_view_active(self) -> bool:
        return self._view == VIEW_QUEUE



    def _build_inventory_studio(self):
        """Constructs the Bin label editor."""
        ctk.CTkLabel(
            self.inventory_studio_frame,
            text="Bin labels are designed for 12 mm tape and always print at 12 mm.",
            font=ctk.CTkFont(size=11),
            text_color=MUTED_TEXT,
            anchor="w",
        ).pack(fill="x", padx=12, pady=(0, 2))
        self.inventory_tab_widget = HardwareInventoryTab(
            self.inventory_studio_frame,
            on_change=self._on_inventory_field_changed,
            on_add_queue=self._on_add_to_queue,
        )
        self.inventory_tab_widget.pack(fill="both", expand=True)

    def _on_inventory_field_changed(self):
        """Triggered when any field in the Bin label editor changes."""
        if hasattr(self, "inventory_tab_widget") and self._view == VIEW_BIN:
            self.config.inventory_config = self.inventory_tab_widget.get_current_inventory_config()
            self._trigger_render()

    def _on_label_language_changed(self, lang: str):
        self.inventory_tab_widget.set_language(lang)
        self.action_status_label.configure(text=f"Bin label language: {LANGUAGES[lang]}")

    # -------------------------------------------------------------------------
    # TEXT LABEL: editor under the preview and the settings panel on the right
    # -------------------------------------------------------------------------
    def _build_text_editor(self, parent):
        top = ctk.CTkFrame(parent, fg_color="transparent")
        top.pack(fill="x", pady=(0, 2))
        ctk.CTkLabel(top, text="Label text", font=ctk.CTkFont(size=13, weight="bold")).pack(side="left")
        ctk.CTkLabel(
            top, text="Enter starts a new line · Ctrl+Enter adds to the queue", text_color=MUTED_TEXT
        ).pack(side="left", padx=12)
        self.btn_clear_text = ctk.CTkButton(
            top,
            text="Clear",
            width=60,
            height=26,
            fg_color="transparent",
            border_width=1,
            text_color=("gray10", "gray90"),
            command=self._on_clear_text,
        )
        self.btn_clear_text.pack(side="right")

        self.text_editor = ctk.CTkTextbox(parent, height=150, font=("Segoe UI", 14), undo=True)
        self.text_editor.pack(fill="x")
        self.text_editor.insert("1.0", "HELLO WORLD\nBrother PT-P300BT")
        self.text_editor.bind("<KeyRelease>", lambda e: self._on_text_changed())
        self.text_editor.bind("<Control-Return>", lambda e: (self._on_add_to_queue(), "break")[1])
        self.text_editor.bind("<Control-KP_Enter>", lambda e: (self._on_add_to_queue(), "break")[1])

    def _build_designer_panel(self, panel):
        # --- Text
        self.section_text = Section(panel, "Text")
        self.section_text.pack(fill="x", pady=(4, 0))
        body = self.section_text.body

        field_label(body, "Font")
        font_row = ctk.CTkFrame(body, fg_color="transparent")
        font_row.pack(fill="x")
        available_fonts = font_manager.get_font_names()
        self.font_combo = ctk.CTkComboBox(
            font_row, values=available_fonts[:40], width=190, command=self._on_font_changed
        )
        self.font_combo.set("Arial" if "Arial" in available_fonts else available_fonts[0])
        self.font_combo.pack(side="left")
        self.btn_browse_font = ctk.CTkButton(font_row, text="Browse…", width=80, command=self._on_browse_font)
        self.btn_browse_font.pack(side="left", padx=(6, 0))

        self.auto_fit_var = ctk.BooleanVar(value=True)
        self.chk_autofit = ctk.CTkCheckBox(
            body, text="Fit to tape height", variable=self.auto_fit_var, command=self._on_autofit_toggle
        )
        self.chk_autofit.pack(anchor="w", pady=(10, 2))
        self.fixed_size_slider, self.fixed_size_val_label = labeled_slider(
            body, "Size", 8, 80, 72, 36, "36 pt", self._on_fixed_size_slide
        )

        field_label(body, "Alignment")
        self.align_seg = ctk.CTkSegmentedButton(
            body, values=["Left", "Center", "Right"], command=self._on_align_changed
        )
        self.align_seg.set("Center")
        self.align_seg.pack(fill="x")

        # --- QR code
        self.section_qr = Section(panel, "QR code", expanded=False)
        self.section_qr.pack(fill="x")
        body = self.section_qr.body
        self.qr_enable_var = ctk.BooleanVar(value=False)
        self.chk_qr_enable = ctk.CTkSwitch(
            body, text="Add a QR code", variable=self.qr_enable_var, command=self._on_qr_toggle
        )
        self.chk_qr_enable.pack(anchor="w", pady=(2, 4))
        field_label(body, "Content: a link, text, or Wi-Fi details")
        self.qr_data_entry = ctk.CTkEntry(body, placeholder_text="https://example.com")
        self.qr_data_entry.pack(fill="x")
        self.qr_data_entry.bind("<KeyRelease>", lambda e: self._on_qr_data_changed())
        field_label(body, "Position")
        self.qr_pos_seg = ctk.CTkSegmentedButton(
            body, values=[POS_LEFT, POS_RIGHT], command=self._on_qr_pos_changed
        )
        self.qr_pos_seg.set(POS_LEFT)
        self.qr_pos_seg.pack(fill="x")
        self.qr_scale_slider, self.qr_scale_label = labeled_slider(
            body, "Size", 0.6, 1.1, 10, 0.95, "95%", self._on_qr_scale_slide
        )
        self.btn_wifi_helper = ctk.CTkButton(body, text="Make a Wi-Fi QR code…", command=self._show_wifi_dialog)
        self.btn_wifi_helper.pack(fill="x", pady=(6, 0))

        # --- Icon or image
        self.section_image = Section(panel, "Icon or image", expanded=False)
        self.section_image.pack(fill="x")
        body = self.section_image.body
        img_buttons = ctk.CTkFrame(body, fg_color="transparent")
        img_buttons.pack(fill="x", pady=(2, 4))
        self.btn_open_icon_lib = ctk.CTkButton(
            img_buttons, text="Icon library…", width=130, command=self._on_open_icon_library
        )
        self.btn_open_icon_lib.pack(side="left")
        self.btn_pick_img = ctk.CTkButton(
            img_buttons,
            text="Choose file…",
            width=120,
            fg_color="transparent",
            border_width=1,
            text_color=("gray10", "gray90"),
            command=self._on_browse_image,
        )
        self.btn_pick_img.pack(side="left", padx=(6, 0))
        img_row = ctk.CTkFrame(body, fg_color="transparent")
        img_row.pack(fill="x")
        self.img_path_label = ctk.CTkLabel(img_row, text="No image", text_color=MUTED_TEXT, anchor="w")
        self.img_path_label.pack(side="left", fill="x", expand=True)
        self.btn_clear_img = ctk.CTkButton(
            img_row, text="Remove", width=70, height=24, fg_color="gray40", command=self._on_clear_image
        )
        self.btn_clear_img.pack(side="right")
        field_label(body, "Position")
        self.img_pos_seg = ctk.CTkSegmentedButton(
            body, values=[POS_LEFT, POS_RIGHT], command=self._on_img_pos_changed
        )
        self.img_pos_seg.set(POS_LEFT)
        self.img_pos_seg.pack(fill="x")
        self.img_scale_slider, self.img_scale_label = labeled_slider(
            body, "Size", 0.3, 1.5, 24, 1.0, "100%", self._on_img_scale_slide
        )

        # --- Length
        self.section_length = Section(panel, "Length")
        self.section_length.pack(fill="x")
        body = self.section_length.body
        field_label(body, "Fixed length in mm, or empty for automatic")
        self.fixed_width_entry = ctk.CTkEntry(body, width=100, placeholder_text="Auto")
        self.fixed_width_entry.pack(anchor="w")
        self.fixed_width_entry.bind("<KeyRelease>", lambda e: self._on_fixed_width_changed())

        # --- Advanced
        self.section_advanced = Section(panel, "Advanced", expanded=False)
        self.section_advanced.pack(fill="x")
        body = self.section_advanced.body
        self.scale_slider, self.scale_val_label = labeled_slider(
            body, "Text scale", 50, 150, 20, 100, "100%", self._on_scale_slide
        )
        self.spacing_slider, self.spacing_val_label = labeled_slider(
            body, "Line spacing", 0.8, 2.0, 24, 1.2, "1.20x", self._on_spacing_slide
        )
        self.padding_slider, self.padding_val_label = labeled_slider(
            body, "Side padding", 0, 40, 40, 8, "8 px", self._on_padding_slide
        )
        self.outline_slider, self.outline_val_label = labeled_slider(
            body, "Outline", 0, 4, 4, 0, "0 px", self._on_outline_slide
        )
        self.threshold_slider, self.threshold_label = labeled_slider(
            body, "Darkness cutoff", 20, 220, 40, 100, "100", self._on_threshold_slide
        )
        field_label(body, "Tape width (set automatically from the printer)")
        self.tape_width_seg = ctk.CTkSegmentedButton(
            body, values=TAPE_WIDTH_OPTIONS, command=self._on_tape_width_changed
        )
        self.tape_width_seg.set("12mm")
        self.tape_width_seg.pack(fill="x")
        field_label(body, "Tape colour in the preview")
        self.color_scheme_combo = ctk.CTkComboBox(
            body, values=list(COLOR_SCHEMES.keys()), command=self._on_color_scheme_changed
        )
        self.color_scheme_combo.set("White Tape / Black Text")
        self.color_scheme_combo.pack(fill="x")
        self.chk_guides_var = ctk.BooleanVar(value=False)
        self.chk_guides = ctk.CTkCheckBox(
            body, text="Show printable area", variable=self.chk_guides_var, command=self._on_guides_toggle
        )
        self.chk_guides.pack(anchor="w", pady=(10, 4))
        self.chk_rulers_var = ctk.BooleanVar(value=False)
        self.chk_rulers = ctk.CTkCheckBox(
            body, text="Show rulers", variable=self.chk_rulers_var, command=self._on_rulers_toggle
        )
        self.chk_rulers.pack(anchor="w", pady=(0, 8))
        # No auto-cut option: the PT-P300BT has a manual cutter and ignores the flag
        # (checked on hardware), so labels keep the default config.auto_cut_hardware.
        self.btn_reset_settings = ctk.CTkButton(
            body, text="Reset settings", fg_color="gray35", hover_color="gray25", command=self._on_reset_settings
        )
        self.btn_reset_settings.pack(fill="x", pady=(4, 0))

    # -------------------------------------------------------------------------
    # QUEUE VIEW
    # -------------------------------------------------------------------------
    def _build_queue_view(self):
        container = self.queue_container_frame
        self._queue_thumbs = {}

        summary = ctk.CTkFrame(container, corner_radius=10)
        summary.pack(fill="x", pady=(0, 6))
        stats_box = ctk.CTkFrame(summary, fg_color="transparent")
        stats_box.pack(fill="x", padx=14, pady=8)

        self.queue_saved_badge = ctk.CTkLabel(
            stats_box, text=QUEUE_EMPTY_HINT, text_color=MUTED_TEXT, anchor="w"
        )
        self.queue_saved_badge.pack(fill="x")

        self.queue_scroll = ctk.CTkScrollableFrame(container, fg_color="transparent")
        self.queue_scroll.pack(fill="both", expand=True)
        self.queue_scroll._parent_canvas.bind("<Configure>", lambda e: self._check_queue_scrollbar(), add="+")
        self.queue_scroll._scrollbar.grid_remove()

        self._refresh_queue_display()

    def _check_queue_scrollbar(self):
        """Shows the queue scrollbar only when items overflow the visible area."""
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

    def _queue_thumbnail(self, cfg: LabelConfig) -> Optional[ctk.CTkImage]:
        """Small picture of a queued label, cached for as long as the label is queued."""
        key = id(cfg)
        if key not in self._queue_thumbs:
            try:
                preview = self.renderer.render(cfg)[0].convert("RGB")
                ratio = QUEUE_THUMB_HEIGHT / preview.height
                size = (max(int(preview.width * ratio), 1), QUEUE_THUMB_HEIGHT)
                if size[0] > QUEUE_THUMB_MAX_WIDTH:
                    size = (QUEUE_THUMB_MAX_WIDTH, max(int(preview.height * QUEUE_THUMB_MAX_WIDTH / preview.width), 1))
                small = preview.resize(size, Image.Resampling.LANCZOS)
                self._queue_thumbs[key] = ctk.CTkImage(light_image=small, dark_image=small, size=size)
            except Exception:
                self._queue_thumbs[key] = None
        return self._queue_thumbs[key]

    def _queue_item_summary(self, cfg: LabelConfig):
        if getattr(cfg, "inventory_config", None) is not None:
            from core.inventory_renderer import FastenerLabelConfig
            inv = cfg.inventory_config
            if isinstance(inv, FastenerLabelConfig):
                return f"{inv.thread_size} {inv.category}", f"Bin label · {inv.label_width_mm:g} mm"
            return f"{inv.category_banner} {inv.spec_primary}", f"Bin label · {inv.label_width_mm:g} mm"
        first_line = cfg.text.strip().splitlines()[0] if cfg.text.strip() else "Image or QR code only"
        if len(first_line) > 40:
            first_line = first_line[:39] + "…"
        details = [format_tape_width(cfg.tape_width_mm), cfg.font_name]
        if cfg.qr_enabled and cfg.qr_data:
            details.append("QR code")
        if cfg.image_path:
            details.append("image")
        return first_line, " · ".join(details)

    def _refresh_queue_display(self):
        """Re-renders the list of queued labels and the summary line."""
        import tkinter
        for child in list(self.queue_scroll.winfo_children()):
            child.destroy()
        try:
            tkinter.Frame.configure(self.queue_scroll, height=1)
            self.queue_scroll._parent_canvas.yview_moveto(0)
        except Exception:
            pass

        count = len(self.label_queue)
        live_ids = {id(c) for c in self.label_queue}
        self._queue_thumbs = {k: v for k, v in self._queue_thumbs.items() if k in live_ids}
        self.sidebar.set_badge(VIEW_QUEUE, count)
        self._update_action_bar()

        if count == 0:
            self.queue_saved_badge.configure(text=QUEUE_EMPTY_HINT, text_color=MUTED_TEXT)

            empty_frame = ctk.CTkFrame(self.queue_scroll, fg_color="transparent")
            empty_frame.pack(fill="both", expand=True, pady=30)
            ctk.CTkLabel(
                empty_frame, text="Your print queue is empty", font=ctk.CTkFont(size=15, weight="bold")
            ).pack(pady=2)
            ctk.CTkLabel(
                empty_frame,
                text="Design a label, then choose Add to queue or press Ctrl+Enter.\n"
                     "Queued labels print as one strip with dotted cut lines between them.",
                text_color=MUTED_TEXT,
                justify="center",
            ).pack(pady=4)
            self._check_queue_scrollbar()
            return

        try:
            _, _, _, b_metrics = self.renderer.render_batch(self.label_queue)
            saved = b_metrics.tape_saved_mm
            if saved > 0:
                self.queue_saved_badge.configure(
                    text=f"Saves {saved:.1f} mm of tape compared with printing {count} labels separately.",
                    text_color="#4CAF50",
                )
            else:
                self.queue_saved_badge.configure(
                    text="Add another label to start saving tape.", text_color=MUTED_TEXT
                )
        except Exception:
            pass

        for idx, cfg in enumerate(self.label_queue):
            row = ctk.CTkFrame(self.queue_scroll, corner_radius=8)
            row.pack(fill="x", pady=3, padx=2)

            ctk.CTkLabel(row, text=f"{idx + 1}", width=24, text_color=MUTED_TEXT).pack(side="left", padx=(10, 4))
            # Fixed-width slot so titles line up whatever the label length
            thumb_slot = ctk.CTkFrame(row, fg_color="transparent", width=QUEUE_THUMB_MAX_WIDTH, height=QUEUE_THUMB_HEIGHT + 8)
            thumb_slot.pack_propagate(False)
            thumb_slot.pack(side="left", padx=(0, 12), pady=6)
            thumb = self._queue_thumbnail(cfg)
            if thumb is not None:
                ctk.CTkLabel(thumb_slot, text="", image=thumb).pack(side="left")

            info_col = ctk.CTkFrame(row, fg_color="transparent")
            info_col.pack(side="left", fill="both", expand=True, pady=6)
            title, details = self._queue_item_summary(cfg)
            ctk.CTkLabel(info_col, text=title, font=ctk.CTkFont(size=13, weight="bold"), anchor="w").pack(anchor="w")
            ctk.CTkLabel(info_col, text=details, font=ctk.CTkFont(size=11), text_color=MUTED_TEXT, anchor="w").pack(
                anchor="w"
            )

            btn_col = ctk.CTkFrame(row, fg_color="transparent")
            btn_col.pack(side="right", padx=8, pady=6)
            small = dict(width=30, height=28, fg_color="transparent", border_width=1, text_color=("gray10", "gray90"))
            ctk.CTkButton(
                btn_col, text="↑", state="disabled" if idx == 0 else "normal",
                command=lambda i=idx: self._on_move_queue_item(i, -1), **small,
            ).pack(side="left", padx=2)
            ctk.CTkButton(
                btn_col, text="↓", state="disabled" if idx == count - 1 else "normal",
                command=lambda i=idx: self._on_move_queue_item(i, 1), **small,
            ).pack(side="left", padx=2)
            ctk.CTkButton(
                btn_col, text="Edit", width=50, height=28, command=lambda i=idx: self._on_load_queue_item(i)
            ).pack(side="left", padx=4)
            ctk.CTkButton(
                btn_col, text="✕", width=30, height=28, fg_color="#C62828", hover_color="#8E0000",
                command=lambda i=idx: self._on_delete_queue_item(i),
            ).pack(side="left", padx=2)

        self._check_queue_scrollbar()

    def _on_add_to_queue(self):
        """Adds the current label to the print queue."""
        if self._view not in (VIEW_TEXT, VIEW_BIN):
            return
        cfg_copy = copy.deepcopy(self.config)

        if getattr(cfg_copy, "inventory_config", None) is not None:
            from core.inventory_renderer import FastenerLabelConfig
            inv = cfg_copy.inventory_config
            if isinstance(inv, FastenerLabelConfig):
                label_summary = f"{inv.thread_size} {inv.category}"
            else:
                label_summary = f"{inv.category_banner} {inv.spec_primary}"
            cfg_copy.text = label_summary
            cfg_copy.tape_width_mm = INVENTORY_TAPE_WIDTH_MM
            first_line = label_summary
        else:
            raw_text = self.text_editor.get("1.0", "end-1c")
            if not raw_text.strip() and not self.config.image_path and not self.config.qr_data:
                self.action_status_label.configure(text="Add some text, a QR code or an image first.")
                return
            cfg_copy.text = raw_text
            first_line = raw_text.strip().splitlines()[0] if raw_text.strip() else "Label"

        # A batch prints as one continuous strip, so every label must share one tape width
        if self.label_queue:
            queue_width = float(self.label_queue[0].tape_width_mm)
            if float(cfg_copy.tape_width_mm) != queue_width:
                messagebox.showwarning(
                    "Different tape width",
                    f"The print queue is for {format_tape_width(queue_width)} tape, but this label is "
                    f"{format_tape_width(cfg_copy.tape_width_mm)}.\n\n"
                    "Print or clear the queue before adding labels for a different tape.",
                )
                return

        self.label_queue.append(cfg_copy)
        self._refresh_queue_display()

        q_len = len(self.label_queue)
        tape_saved = TAPE_LEAD_MM * (q_len - 1)
        if len(first_line) > 25:
            first_line = first_line[:24] + "…"
        if q_len > 1:
            msg = f"Added '{first_line}' to the queue ({q_len} labels, saves {tape_saved:.0f} mm of tape)"
        else:
            msg = f"Added '{first_line}' to the queue"
        self.action_status_label.configure(text=msg)

    def _on_move_queue_item(self, index: int, direction: int):
        new_idx = index + direction
        if 0 <= new_idx < len(self.label_queue):
            self.label_queue[index], self.label_queue[new_idx] = (
                self.label_queue[new_idx],
                self.label_queue[index],
            )
            self._refresh_queue_display()
            self._trigger_render()

    def _on_delete_queue_item(self, index: int):
        if 0 <= index < len(self.label_queue):
            del self.label_queue[index]
            self._refresh_queue_display()
            self._trigger_render()
            self.action_status_label.configure(text=f"Removed from the queue ({len(self.label_queue)} left)")

    def _on_clear_queue(self):
        if not self.label_queue:
            return
        if messagebox.askyesno("Clear queue", f"Remove all {len(self.label_queue)} labels from the print queue?"):
            self.label_queue.clear()
            self._refresh_queue_display()
            self._trigger_render()
            self.action_status_label.configure(text="Queue cleared")

    def _on_load_queue_item(self, index: int):
        """Opens a queued label in its editor (the queued copy stays in the queue)."""
        if 0 <= index < len(self.label_queue):
            cfg = copy.deepcopy(self.label_queue[index])
            if getattr(cfg, "inventory_config", None) is not None:
                self._show_view(VIEW_BIN)
                self.config = cfg
                self.inventory_tab_widget.load_inventory_config(cfg.inventory_config)
            else:
                # Switch first: showing the view re-reads the editor into the current config
                self._show_view(VIEW_TEXT)
                self.config = cfg
                self._update_ui_from_config(cfg)
            self._trigger_render()
            self.action_status_label.configure(text=f"Editing queued label {index + 1}")

    def _update_ui_from_config(self, cfg: LabelConfig):
        """Populates the text label editor and panel from a LabelConfig."""
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
            self.spacing_val_label.configure(text=f"{cfg.line_spacing:.2f}x")
            pad = getattr(cfg, "h_padding", getattr(cfg, "h_padding_dots", 8))
            self.padding_slider.set(pad)
            self.padding_val_label.configure(text=f"{pad} px")
            self.threshold_slider.set(cfg.threshold)
            self.threshold_label.configure(text=str(cfg.threshold))

            self.qr_enable_var.set(cfg.qr_enabled)
            self.qr_data_entry.delete(0, "end")
            if cfg.qr_data:
                self.qr_data_entry.insert(0, cfg.qr_data)
            self.qr_pos_seg.set(POS_LEFT if cfg.qr_position == "left" else POS_RIGHT)
            self.qr_scale_slider.set(cfg.qr_scale)
            self.qr_scale_label.configure(text=f"{int(cfg.qr_scale * 100)}%")
            if cfg.qr_enabled:
                self.section_qr.set_expanded(True)

            self.img_path_label.configure(
                text=os.path.basename(cfg.image_path) if cfg.image_path else "No image"
            )
            self.img_pos_seg.set(POS_LEFT if cfg.image_position == "left" else POS_RIGHT)
            self.img_scale_slider.set(cfg.image_scale)
            self.img_scale_label.configure(text=f"{int(cfg.image_scale * 100)}%")
            if cfg.image_path:
                self.section_image.set_expanded(True)

            tw_str = format_tape_width(cfg.tape_width_mm)
            if tw_str in TAPE_WIDTH_OPTIONS:
                self.tape_width_seg.set(tw_str)

            self.config.tape_bg_color = cfg.tape_bg_color
            self.config.tape_fg_color = cfg.tape_fg_color
            scheme = next(
                (name for name, colors in COLOR_SCHEMES.items() if colors == (cfg.tape_bg_color, cfg.tape_fg_color)),
                "White Tape / Black Text",
            )
            self.color_scheme_combo.set(scheme)

            self.fixed_width_entry.delete(0, "end")
            if cfg.fixed_width_mm:
                self.fixed_width_entry.insert(0, f"{cfg.fixed_width_mm:g}")

            self.chk_guides_var.set(cfg.show_guides)
            self.chk_rulers_var.set(cfg.show_rulers)
        finally:
            self._updating_ui_from_config = False

    # =========================================================================
    # BOTTOM ACTION BAR
    # =========================================================================
    def _setup_action_bar(self):
        """Print (the one main action), Add to queue, a "more" menu, and the status line."""
        self.action_frame = ctk.CTkFrame(self, corner_radius=10)
        self.action_frame.pack(side="bottom", fill="x", padx=12, pady=(0, 10))

        inner = ctk.CTkFrame(self.action_frame, fg_color="transparent")
        inner.pack(fill="x", padx=12, pady=10)

        self.btn_print = ctk.CTkButton(
            inner,
            text="Print",
            font=ctk.CTkFont(size=13, weight="bold"),
            height=38,
            width=150,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            text_color="white",
            text_color_disabled="gray80",
            command=self._on_print_clicked,
        )
        self.btn_print.pack(side="left")

        self.btn_add_queue = ctk.CTkButton(
            inner,
            text="Add to queue",
            height=38,
            width=130,
            fg_color="transparent",
            border_width=1,
            text_color=("gray10", "gray90"),
            command=self._on_add_to_queue,
        )
        self.btn_add_queue.pack(side="left", padx=(8, 0))

        self.btn_more = ctk.CTkButton(
            inner,
            text="•••",
            height=38,
            width=44,
            fg_color="transparent",
            border_width=1,
            text_color=("gray10", "gray90"),
            command=self._show_more_menu,
        )
        self.btn_more.pack(side="left", padx=(8, 0))

        status_box = ctk.CTkFrame(inner, fg_color="transparent")
        status_box.pack(side="right", fill="x", expand=True, padx=(16, 0))
        self.progress_bar = ctk.CTkProgressBar(status_box, height=10)
        self.progress_bar.set(0.0)
        self.action_status_label = ctk.CTkLabel(
            status_box, text="Ready", font=ctk.CTkFont(size=12), text_color=MUTED_TEXT, anchor="w"
        )
        self.action_status_label.pack(fill="x")

    def _show_more_menu(self):
        menu = tk.Menu(self, tearoff=0)
        busy = "disabled" if self.is_printing else "normal"
        menu.add_command(label="Export PNG…        Ctrl+S", command=self._on_export_png)
        menu.add_command(label=f"Feed {FEED_LENGTH_MM:.0f} mm of tape", command=self._on_feed_tape_clicked, state=busy)
        if self._view == VIEW_QUEUE:
            menu.add_separator()
            menu.add_command(
                label="Clear queue", command=self._on_clear_queue,
                state="normal" if self.label_queue and not self.is_printing else "disabled",
            )
        x = self.btn_more.winfo_rootx()
        y = self.btn_more.winfo_rooty() - (len(menu.winfo_children()) + 3) * 24
        try:
            menu.tk_popup(x, max(y, 0))
        finally:
            menu.grab_release()

    def _update_action_bar(self):
        """Matches the main button to the current view."""
        if not hasattr(self, "btn_print") or not hasattr(self, "sidebar"):
            return
        state = "disabled" if self.is_printing else "normal"
        if self._view == VIEW_QUEUE:
            count = len(self.label_queue)
            if not self.btn_print.winfo_ismapped():
                self.btn_print.pack(side="left", before=self.btn_more)
            self.btn_print.configure(
                text=f"Print queue ({count})" if count else "Print queue",
                state="normal" if count and not self.is_printing else "disabled",
            )
            self.btn_add_queue.pack_forget()
        elif self._view in (VIEW_TEXT, VIEW_BIN):
            self.btn_print.configure(text="Print", state=state)
            if not self.btn_print.winfo_ismapped():
                self.btn_print.pack(side="left", before=self.btn_more)
            if not self.btn_add_queue.winfo_ismapped():
                self.btn_add_queue.pack(side="left", padx=(8, 0), after=self.btn_print)
            self.btn_add_queue.configure(state=state)
        else:
            self.btn_print.pack_forget()
            self.btn_add_queue.pack_forget()

    # =========================================================================
    # EVENT HANDLERS & RENDERING
    # =========================================================================

    def _trigger_render(self):
        """Re-renders the preview: the whole strip in the queue view, otherwise the current label."""
        if self._updating_ui_from_config or not hasattr(self, "preview_widget"):
            return

        try:
            if self._view == VIEW_QUEUE and self.label_queue:
                prev_img, rast_img, r_bytes, metrics = self.renderer.render_batch(self.label_queue)
            else:
                # Read text if standard text label
                if getattr(self.config, "inventory_config", None) is None:
                    self.config.text = self.text_editor.get("1.0", "end-1c")
                prev_img, rast_img, r_bytes, metrics = self.renderer.render(self.config)
            self._current_preview = prev_img
            self._current_raster = rast_img
            self._current_raster_bytes = r_bytes
            self._current_metrics = metrics

            self.preview_widget.update_content(prev_img, rast_img, metrics, tape_spec=self._tape_spec_for_preview())
            if self._view == VIEW_TEXT:
                self._sync_size_controls()
        except Exception as e:
            self.action_status_label.configure(text=f"Couldn't draw the label: {e}")

    def _tape_spec_for_preview(self) -> dict:
        from core.specs import get_tape_spec
        if self._view == VIEW_QUEUE and self.label_queue:
            width = self.label_queue[0].tape_width_mm
        elif getattr(self.config, "inventory_config", None) is not None:
            width = INVENTORY_TAPE_WIDTH_MM
        else:
            width = self.config.tape_width_mm
        try:
            return get_tape_spec(width)
        except ValueError:
            return get_tape_spec(12)

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

    def _sync_size_controls(self):
        """The size slider only applies when auto-fit is off; say so instead of ignoring it."""
        if not hasattr(self, "fixed_size_slider"):
            return
        if self.config.auto_fit_font:
            self.fixed_size_slider.configure(state="disabled")
            size = self._current_metrics.effective_font_size if self._current_metrics else None
            self.fixed_size_val_label.configure(text=f"Auto ({size} pt)" if size else "Auto")
        else:
            self.fixed_size_slider.configure(state="normal")
            self.fixed_size_val_label.configure(text=f"{self.config.fixed_font_size} pt")

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
            self._set_custom_designer_image(p)

    def _set_custom_designer_image(self, path: str):
        if path and os.path.isfile(path):
            self.config.image_path = path
            self.img_path_label.configure(text=os.path.basename(path))
            self.section_image.set_expanded(True)
            self._trigger_render()

    def _on_open_icon_library(self):
        IconBrowserDialog(
            self,
            on_select=self._set_custom_designer_image,
            title_suffix="Custom Designer",
            on_open_ai_generator=self._on_open_ai_generator,
        )

    def _on_open_ai_generator(self):
        AIGeneratorDialog(
            self,
            on_save_callback=self._set_custom_designer_image,
        )

    def _on_clear_image(self):
        self.config.image_path = None
        self.img_path_label.configure(text="No image")
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
        self.config.tape_width_mm = float(value.replace("mm", ""))
        self._trigger_render()

    def _on_color_scheme_changed(self, value: str):
        if value in COLOR_SCHEMES:
            bg, fg = COLOR_SCHEMES[value]
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

    def _on_reset_settings(self, confirm: bool = True):
        """Resets all configuration settings back to defaults (keeps the label text)."""
        if confirm and not messagebox.askyesno(
            "Reset settings",
            "Reset font, size, QR code, image and tape settings to their defaults? "
            "Your label text is kept.",
        ):
            return
        cur_text = self.text_editor.get("1.0", "end-1c")
        self.config = LabelConfig(
            text=cur_text,
            auto_cut_hardware=True,
            cut_line=False,
        )
        self._update_ui_from_config(self.config)
        self._trigger_render()
        self.action_status_label.configure(text="Settings reset")

    # -------------------------------------------------------------------------
    # TEMPLATES & PRESETS
    # -------------------------------------------------------------------------
    def _apply_preset_and_edit(self, name: str):
        """Opens a template in the text label editor."""
        self._show_view(VIEW_TEXT)
        self._apply_preset(name)
        self.action_status_label.configure(text=f"Started from the '{name}' template")

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
                self.qr_pos_seg.set(POS_LEFT if self.config.qr_position == "left" else POS_RIGHT)
                self.section_qr.set_expanded(True)

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
                self.action_status_label.configure(text=f"Saved {os.path.basename(p)}")
            else:
                messagebox.showerror("Couldn't save template", f"The template couldn't be written to:\n{p}")

    def _on_load_template(self):
        p = filedialog.askopenfilename(
            title="Open Label Template",
            filetypes=[("JSON Files", "*.json")],
        )
        if p and os.path.isfile(p):
            try:
                cfg = load_config_from_json(p)
            except (OSError, ValueError) as e:
                messagebox.showerror("Could Not Load Template", str(e))
                return
            if cfg.inventory_config is not None:
                self._show_view(VIEW_BIN)
                self.config = cfg
                self.inventory_tab_widget.load_inventory_config(cfg.inventory_config)
            else:
                # Switch first: showing the view re-reads the editor into the current config
                self._show_view(VIEW_TEXT)
                self.config = cfg
                self._update_ui_from_config(cfg)
            self._trigger_render()
            self.action_status_label.configure(text=f"Opened {os.path.basename(p)}")

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
            elif config_manager.last_serial_port and config_manager.last_serial_port in self._port_device_to_label:
                # 2. If remembered port from config is available, use it!
                target_device = config_manager.last_serial_port
            else:
                # 3. Prefer Brother Outgoing printer port (is_preferred=True)
                for p in ports:
                    if p.is_preferred:
                        target_device = p.device
                        break
                # 4. If none preferred, take first non-incoming port
                if not target_device:
                    for p in ports:
                        if not p.is_incoming:
                            target_device = p.device
                            break
                # 5. Fallback to first available port
                if not target_device:
                    target_device = ports[0].device

            target_label = self._port_device_to_label[target_device]
            self.port_combo.set(target_label)
            self.port_var.set(target_label)
            self._selected_port_device = target_device
            config_manager.last_serial_port = target_device


            # Auto-query status if physical mode
            if not self.virtual_mode_var.get():
                self._on_query_status()

    def _on_port_selected(self, value: str):
        if value and value != "No Ports Found":
            if value in self._port_label_to_device:
                self._selected_port_device = self._port_label_to_device[value]
            else:
                self._selected_port_device = value.split()[0]
            config_manager.last_serial_port = self._selected_port_device

            if not self.virtual_mode_var.get():
                self._on_query_status()

    def _on_virtual_mode_toggle(self):
        if self.virtual_mode_var.get():
            self.printer_chip.set_state("simulation", "Simulation")
            self.printer_panel.set_details(["Printing is simulated. Nothing is sent to a printer."])
            self.action_status_label.configure(text="Ready (simulation)")
            self._on_query_status()
        else:
            self.printer_chip.set_state("connecting", "Connecting…")
            self.printer_panel.set_details(["Connecting to the printer…"])
            self.action_status_label.configure(text="Connecting to the printer…")
            self._on_query_status()

    def _get_selected_port(self) -> Optional[str]:
        """Returns the selected COM port device, or None if no valid port is selected."""
        port = getattr(self, "_selected_port_device", None)
        if not port:
            cur_val = self.port_var.get()
            if cur_val and cur_val != "No Ports Found":
                port = cur_val.split()[0]
        return port

    def _is_hardware_studio_active(self) -> bool:
        return (
            hasattr(self, "inventory_studio_frame")
            and self.inventory_studio_frame.winfo_manager() == "pack"
        )

    def _on_query_status(self):
        """Asynchronously queries printer hardware status."""
        # Never open the port while a print job owns it
        if self.is_printing:
            return

        self.action_status_label.configure(text="Checking the printer…")

        is_virt = self.virtual_mode_var.get()
        port = None if is_virt else self._get_selected_port()

        def _worker(virt_mode=is_virt, port_name=port):
            try:
                if virt_mode:
                    printer = MockBrotherPrinter()
                    status = printer.get_status()
                else:
                    if not port_name:
                        raise RuntimeError("Please select a valid COM port from the dropdown.")
                    printer = BrotherPrinter(port_name)
                    status = printer.get_status()

                self._post_to_main(lambda s=status: self._apply_telemetry(s))
            except Exception as e:
                err_msg = str(e)
                self._post_to_main(lambda m=err_msg: self._handle_query_error(m))

        threading.Thread(target=_worker, daemon=True).start()

    def _apply_telemetry(self, status: PrinterStatus):
        loaded_width = tape_width_from_status(status.tape_width_mm)
        tw_str = format_tape_width(loaded_width)
        tape_text = f"{tw_str} {status.bg_color_name.lower()}" if status.tape_loaded else "no tape"
        power = status.power_status.lower()

        if status.is_ready:
            problems = ""
        elif status.errors:
            problems = ", ".join(status.errors)
        elif not status.tape_loaded:
            problems = "No tape loaded"
        else:
            problems = status.phase_name

        if self.virtual_mode_var.get():
            self.printer_chip.set_state("simulation", f"Simulation · {tape_text}")
        elif status.is_ready:
            self.printer_chip.set_state("ready", f"{status.model_name} · {tape_text} · {power}")
        else:
            self.printer_chip.set_state("problem", f"{status.model_name} · {problems}")

        details = [
            f"{status.model_name}{' (simulated)' if self.virtual_mode_var.get() else ''}",
            f"Tape: {tw_str} {status.tape_type_name}, {status.bg_color_name} with {status.fg_color_name} text"
            if status.tape_loaded else "Tape: none loaded",
            f"Power: {status.power_status}",
        ]
        if problems:
            details.append(f"Not ready: {problems}")
        self.printer_panel.set_details(details)

        # Follow the loaded tape
        if tw_str in TAPE_WIDTH_OPTIONS:
            self.tape_width_seg.set(tw_str)
            self.config.tape_width_mm = loaded_width
        self.config.tape_bg_color = status.bg_color_hex
        self.config.tape_fg_color = status.fg_color_hex
        self._trigger_render()

        msg = "Ready" if status.is_ready else f"Printer not ready: {problems}"
        if self._view == VIEW_BIN and loaded_width != INVENTORY_TAPE_WIDTH_MM:
            msg += f". Bin labels need {format_tape_width(INVENTORY_TAPE_WIDTH_MM)} tape; {tw_str} is loaded."
        self.action_status_label.configure(text=msg)

    def _handle_query_error(self, err: str):
        self.printer_chip.set_state("problem", "Printer not found")
        self.printer_panel.set_details([
            "Couldn't reach the printer.",
            err,
            "Check that it's switched on and paired, then choose Check status.",
        ])
        self.action_status_label.configure(text="Printer not found. Click the printer chip for details.")

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

    def _exceeds_max_length(self, metrics: Optional[LabelMetrics]) -> bool:
        """Shows an error and returns True if the label is longer than the printer allows."""
        if metrics and metrics.total_used_length_mm > LabelRenderer.MAX_TOTAL_LENGTH_MM:
            messagebox.showerror(
                "Label Too Long",
                f"This label needs {metrics.total_used_length_mm:.0f} mm of tape, but the printer's "
                f"limit is {LabelRenderer.MAX_TOTAL_LENGTH_MM:.0f} mm. Shorten it or split the queue.",
            )
            return True
        return False

    def _set_busy(self, busy: bool):
        """Disables printer actions while a job runs and shows the progress bar only then."""
        self.is_printing = busy
        self.btn_more.configure(state="disabled" if busy else "normal")
        if busy:
            self.progress_bar.set(0.0)
            self.progress_bar.pack(fill="x", pady=(2, 4), before=self.action_status_label)
        else:
            self.progress_bar.pack_forget()
        self._update_action_bar()

    def _run_printer_job(
        self,
        job: Callable,
        on_success: Callable[[PrinterStatus], None],
        progress_text: Callable[[int, int], str],
    ) -> bool:
        """
        Runs job(printer, progress_cb, status_cb) on a worker thread against the selected
        printer, posting results back to the Tk main loop. Returns False if it did not start.
        """
        if self.is_printing:
            return False

        is_virt = self.virtual_mode_var.get()
        port = None if is_virt else self._get_selected_port()
        if not is_virt and not port:
            messagebox.showerror("No Printer", "No serial COM port selected. Check Bluetooth pairing.")
            return False

        self._set_busy(True)

        def _prog(cur, total):
            pct = cur / total if total else 1.0
            self._post_to_main(lambda p=pct, m=progress_text(cur, total): self._update_progress(p, m))

        def _stat(msg):
            self._post_to_main(lambda m=msg: self.action_status_label.configure(text=m))

        def _worker():
            try:
                printer = MockBrotherPrinter() if is_virt else BrotherPrinter(port)
                status = job(printer, _prog, _stat)
                self._post_to_main(lambda s=status: on_success(s))
            except Exception as e:
                err_msg = str(e)
                self._post_to_main(lambda m=err_msg: self._print_failure(m))

        threading.Thread(target=_worker, daemon=True).start()
        return True

    def _on_print_clicked(self):
        if self._view not in (VIEW_TEXT, VIEW_BIN, VIEW_QUEUE):
            return
        # In the queue view, Print prints the whole queue
        if self._view == VIEW_QUEUE:
            if self.label_queue:
                self._on_print_batch_clicked()
            return

        if self.is_printing:
            return

        if not self._current_raster_bytes:
            messagebox.showwarning("Warning", "No label data to print.")
            return

        if self._exceeds_max_length(self._current_metrics):
            return

        auto_cut = self.config.auto_cut_hardware
        data = self._current_raster_bytes
        required_width = (
            INVENTORY_TAPE_WIDTH_MM if getattr(self.config, "inventory_config", None) is not None else None
        )

        def _job(printer, prog, stat):
            return printer.print_raster_data(
                data,
                auto_cut=auto_cut,
                progress_callback=prog,
                status_callback=stat,
                required_tape_width_mm=required_width,
            )

        self._run_printer_job(
            _job,
            on_success=self._print_success,
            progress_text=lambda c, t: f"Sending data: {c}/{t} lines...",
        )

    def _on_feed_tape_clicked(self):
        """Advances the tape past the manual cutter blade."""
        def _job(printer, prog, stat):
            return printer.feed_tape(FEED_LENGTH_MM, status_callback=stat)

        self._run_printer_job(
            _job,
            on_success=self._feed_success,
            progress_text=lambda c, t: f"Feeding tape: {c}/{t}...",
        )

    def _update_progress(self, pct: float, msg: str):
        self.progress_bar.set(pct)
        self.action_status_label.configure(text=msg)

    def _feed_success(self, status: PrinterStatus):
        self._set_busy(False)
        self.action_status_label.configure(text=f"Fed {FEED_LENGTH_MM:.0f} mm of tape to the cutter.")

    def _print_success(self, status: PrinterStatus):
        self._set_busy(False)
        if status.completion_confirmed:
            self.action_status_label.configure(text="Printed")
        else:
            self.action_status_label.configure(
                text="Print sent, but the printer did not confirm completion. Check the label."
            )

    def _print_failure(self, err_msg: str):
        self._set_busy(False)
        self.action_status_label.configure(text=f"Print failed: {err_msg}")
        messagebox.showerror("Printing Error", err_msg)

    def _on_print_batch_clicked(self):
        """Prints the entire queued list of labels as one continuous strip."""
        if not self.label_queue:
            messagebox.showinfo("Queue Empty", "Please add at least one label to the queue before printing.")
            return

        if self.is_printing:
            return

        try:
            prev_img, rast_img, r_bytes, metrics = self.renderer.render_batch(self.label_queue)
        except Exception as e:
            messagebox.showerror("Render Error", f"Failed to generate batch raster data: {e}")
            return

        if self._exceeds_max_length(metrics):
            return

        # The batch is one strip with one cut at the end, so it follows the current auto-cut setting
        auto_cut = self.config.auto_cut_hardware
        label_count = len(self.label_queue)
        tape_saved_mm = metrics.tape_saved_mm
        required_width = (
            INVENTORY_TAPE_WIDTH_MM
            if any(getattr(c, "inventory_config", None) is not None for c in self.label_queue)
            else None
        )

        def _job(printer, prog, stat):
            return printer.print_raster_data(
                r_bytes,
                auto_cut=auto_cut,
                progress_callback=prog,
                status_callback=stat,
                required_tape_width_mm=required_width,
            )

        self._run_printer_job(
            _job,
            on_success=lambda s: self._batch_print_success(s, label_count, tape_saved_mm),
            progress_text=lambda c, t: f"Printing batch ({label_count} labels): {c}/{t} lines...",
        )

    def _batch_print_success(self, status: PrinterStatus, count: int, tape_saved: float):
        self._set_busy(False)

        if not status.completion_confirmed:
            self.action_status_label.configure(
                text=f"Queue of {count} labels sent, but the printer did not confirm completion."
            )
            return

        self.action_status_label.configure(text=f"Printed {count} labels")
        if messagebox.askyesno("Queue printed", f"Printed {count} labels as one strip.\n\nClear the print queue?"):
            self.label_queue.clear()
            self._refresh_queue_display()
            self._trigger_render()

def main():
    app = PrintLabelApp()
    app.mainloop()


if __name__ == "__main__":
    main()
