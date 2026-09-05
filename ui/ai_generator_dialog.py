#!/usr/bin/env python3
"""
AI Wireframe Generator Dialog for Brother PT-P300BT Label Studio.
Provides:
1. Photo-to-Wireframe using Gemini Vision / Image generation
2. Text-to-Wireframe description generator
3. Offline Local Edge Filter with live slider controls
4. Save directly into user icon library & immediate label insertion
"""

import os
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Callable, Optional
import customtkinter as ctk
from PIL import Image

from core.config import config_manager
from core.ai_generator import (
    ai_generator,
    local_edge_filter,
    post_process_thermal,
    THERMAL_WIREFRAME_SYSTEM_PROMPT,
)
from core.icon_manager import icon_manager


class AIGeneratorDialog(ctk.CTkToplevel):
    """Modal dialog for generating thermal wireframe icons using Gemini AI or local filters."""

    def __init__(self, parent, on_save_callback: Optional[Callable[[str], None]] = None):
        super().__init__(parent)
        self.on_save_callback = on_save_callback

        self.title("✨ AI Wireframe & Line-Art Generator")
        self.geometry("880x680")
        self.minsize(780, 580)

        self.transient(parent)
        self.grab_set()

        # State
        self.source_image: Optional[Image.Image] = None
        self.source_path: Optional[str] = None
        self.raw_unprocessed_image: Optional[Image.Image] = None
        self.generated_image: Optional[Image.Image] = None
        self._ctk_preview_img: Optional[ctk.CTkImage] = None
        self._ctk_source_thumb: Optional[ctk.CTkImage] = None
        self.is_generating = False

        self._build_ui()

    def _build_ui(self):
        # 1. Header
        header = ctk.CTkFrame(self, corner_radius=0)
        header.pack(fill="x", padx=16, pady=(12, 6))

        title_lbl = ctk.CTkLabel(
            header,
            text="✨ AI Monochrome Wireframe Generator",
            font=ctk.CTkFont(size=18, weight="bold"),
        )
        title_lbl.pack(anchor="w")

        desc_lbl = ctk.CTkLabel(
            header,
            text="Convert photos or descriptions into pure black-and-white line-art icons ready for thermal printing.",
            font=ctk.CTkFont(size=12),
            text_color="gray70",
        )
        desc_lbl.pack(anchor="w")

        # 2. Main Content Split: Left Controls / Right Preview
        content_frame = ctk.CTkFrame(self, fg_color="transparent")
        content_frame.pack(fill="both", expand=True, padx=16, pady=6)

        left_frame = ctk.CTkFrame(content_frame, width=480)
        left_frame.pack(side="left", fill="both", expand=True, padx=(0, 8))

        right_frame = ctk.CTkFrame(content_frame, width=340)
        right_frame.pack(side="right", fill="both", padx=(8, 0))

        # --- Left Side: Tabview for Generation Modes ---
        self.tabview = ctk.CTkTabview(left_frame)
        self.tabview.pack(fill="both", expand=True, padx=8, pady=8)

        self.tab_photo = self.tabview.add("📷 Photo to Wireframe")
        self.tab_text = self.tabview.add("✍ Text to Wireframe")
        self.tab_local = self.tabview.add("⚡ Offline Edge Filter")
        self.tab_import = self.tabview.add("📥 Clean & Import Image")

        self._build_tab_photo()
        self._build_tab_text()
        self._build_tab_local()
        self._build_tab_import()

        # --- API Key Section below tabs ---
        api_frame = ctk.CTkFrame(left_frame)
        api_frame.pack(fill="x", padx=8, pady=(0, 8))

        api_top = ctk.CTkFrame(api_frame, fg_color="transparent")
        api_top.pack(fill="x", padx=10, pady=(6, 2))

        ctk.CTkLabel(
            api_top,
            text="Google Gemini API Key:",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(side="left")

        btn_get_key = ctk.CTkButton(
            api_top,
            text="Get Free Key ↗",
            width=90,
            height=20,
            fg_color="transparent",
            text_color="#38BDF8",
            hover_color="gray25",
            font=ctk.CTkFont(size=11, underline=True),
            command=self._open_ai_studio_link,
        )
        btn_get_key.pack(side="right")

        api_input_row = ctk.CTkFrame(api_frame, fg_color="transparent")
        api_input_row.pack(fill="x", padx=10, pady=(0, 6))

        self.entry_api_key = ctk.CTkEntry(
            api_input_row,
            placeholder_text="Enter Gemini API Key (saved locally in ~/.printlabel/config.json)",
            show="•",
            font=ctk.CTkFont(size=12),
        )
        self.entry_api_key.pack(side="left", fill="x", expand=True, padx=(0, 6))
        if config_manager.gemini_api_key:
            self.entry_api_key.insert(0, config_manager.gemini_api_key)

        btn_save_key = ctk.CTkButton(
            api_input_row,
            text="Save Key",
            width=75,
            command=self._save_api_key,
        )
        btn_save_key.pack(side="right")

        # --- Right Side: Preview & Save ---
        self._build_preview_panel(right_frame)

    def _open_ai_studio_link(self):
        import webbrowser
        webbrowser.open("https://aistudio.google.com/app/apikey")

    def _save_api_key(self):
        key = self.entry_api_key.get().strip()
        config_manager.gemini_api_key = key
        ai_generator.api_key = key
        messagebox.showinfo("Gemini API", "API key saved successfully!")

    def _build_tab_photo(self):
        # 1. Source Image Picker
        picker_frame = ctk.CTkFrame(self.tab_photo, fg_color="transparent")
        picker_frame.pack(fill="x", pady=6)

        btn_browse = ctk.CTkButton(
            picker_frame,
            text="📂 Choose Part Photo...",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._browse_source_image,
        )
        btn_browse.pack(side="left", padx=(0, 8))

        self.lbl_source_filename = ctk.CTkLabel(
            picker_frame,
            text="No photo selected",
            font=ctk.CTkFont(size=12),
            text_color="gray70",
        )
        self.lbl_source_filename.pack(side="left")

        # Thumbnail display of source photo
        self.lbl_source_thumb = ctk.CTkLabel(
            self.tab_photo,
            text="[ Photo Preview ]",
            width=140,
            height=120,
            fg_color="gray15",
            corner_radius=6,
        )
        self.lbl_source_thumb.pack(pady=4)

        # Prompt / Style
        ctk.CTkLabel(
            self.tab_photo,
            text="Style Preset:",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(anchor="w", pady=(6, 2))

        self.style_var = tk.StringVar(value="Isometric Technical Wireframe (Recommended)")
        self.combo_style = ctk.CTkComboBox(
            self.tab_photo,
            values=[
                "Isometric Technical Wireframe (Recommended)",
                "Top-Down Blueprint Outline",
                "Monochrome Silhouette",
                "Schematic Vector Symbol",
            ],
            variable=self.style_var,
        )
        self.combo_style.pack(fill="x", pady=(0, 6))

        ctk.CTkLabel(
            self.tab_photo,
            text="Extra Details / Instructions (Optional):",
            font=ctk.CTkFont(size=12),
        ).pack(anchor="w", pady=(2, 2))

        self.entry_photo_details = ctk.CTkEntry(
            self.tab_photo,
            placeholder_text="e.g. emphasize lever clips, 3 ports, DIN markings",
            font=ctk.CTkFont(size=12),
        )
        self.entry_photo_details.pack(fill="x", pady=(0, 10))

        # Billing / Quota note
        ctk.CTkLabel(
            self.tab_photo,
            text="💡 Note: Direct Gemini *-image API calls require billing enabled on your Google AI Studio project (free-tier quota is 0). If unbilled, use '⚡ Offline Edge Filter' (100% free locally) or generate in Gemini Web Chat and use '📥 Clean & Import'.",
            font=ctk.CTkFont(size=11),
            text_color="#FBBF24",
            wraplength=420,
            justify="left",
        ).pack(fill="x", pady=(4, 6))

        # Generate Button
        self.btn_gen_photo = ctk.CTkButton(
            self.tab_photo,
            text="✨ Generate AI Wireframe (Gemini)",
            height=40,
            fg_color="#8B5CF6",
            hover_color="#7C3AED",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._generate_from_photo,
        )
        self.btn_gen_photo.pack(fill="x", pady=4)

    def _build_tab_text(self):
        ctk.CTkLabel(
            self.tab_text,
            text="Describe the Component or Tool:",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(anchor="w", pady=(8, 4))

        self.entry_text_prompt = ctk.CTkTextbox(
            self.tab_text,
            height=90,
            font=ctk.CTkFont(size=13),
        )
        self.entry_text_prompt.pack(fill="x", pady=(0, 10))
        self.entry_text_prompt.insert(
            "1.0",
            "WAGO 221 lever splicing connector 3-wire with orange levers in isometric view",
        )

        ctk.CTkLabel(
            self.tab_text,
            text="Examples: 'M3 nylon lock nut', 'NEMA 17 stepper motor', 'USB Type-C female SMD port', 'rotary encoder'",
            font=ctk.CTkFont(size=11),
            text_color="gray70",
            wraplength=420,
        ).pack(anchor="w", pady=(0, 12))

        self.btn_gen_text = ctk.CTkButton(
            self.tab_text,
            text="✨ Generate from Description (Imagen / Gemini)",
            height=40,
            fg_color="#8B5CF6",
            hover_color="#7C3AED",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._generate_from_text,
        )
        self.btn_gen_text.pack(fill="x", pady=4)

    def _build_tab_local(self):
        ctk.CTkLabel(
            self.tab_local,
            text="Offline Local Edge Filter (No Internet or API Key Needed)",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(anchor="w", pady=(6, 2))

        ctk.CTkLabel(
            self.tab_local,
            text="Extracts high-contrast line-art contours locally from any photo.",
            font=ctk.CTkFont(size=11),
            text_color="gray70",
        ).pack(anchor="w", pady=(0, 8))

        btn_browse_local = ctk.CTkButton(
            self.tab_local,
            text="📂 Select Photo for Local Filter...",
            command=self._browse_source_image,
        )
        btn_browse_local.pack(fill="x", pady=(0, 8))

        # Quick Presets Row
        presets_row = ctk.CTkFrame(self.tab_local, fg_color="transparent")
        presets_row.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(presets_row, text="Presets:", font=ctk.CTkFont(size=11, weight="bold")).pack(side="left", padx=(0, 4))
        ctk.CTkButton(
            presets_row, text="Technical", width=80, height=24, font=ctk.CTkFont(size=11),
            command=lambda: self._set_local_preset(130, 2)
        ).pack(side="left", padx=2)
        ctk.CTkButton(
            presets_row, text="Bold Outline", width=90, height=24, font=ctk.CTkFont(size=11),
            command=lambda: self._set_local_preset(175, 3)
        ).pack(side="left", padx=2)
        ctk.CTkButton(
            presets_row, text="Fine Detail", width=80, height=24, font=ctk.CTkFont(size=11),
            command=lambda: self._set_local_preset(85, 1)
        ).pack(side="left", padx=2)

        # Sensitivity Slider
        ctk.CTkLabel(
            self.tab_local,
            text="Edge Sensitivity (Detail Level):",
            font=ctk.CTkFont(size=12),
        ).pack(anchor="w")

        self.slider_sens = ctk.CTkSlider(
            self.tab_local,
            from_=30,
            to=220,
            number_of_steps=19,
            command=lambda val: self._apply_local_filter(),
        )
        self.slider_sens.set(130)
        self.slider_sens.pack(fill="x", pady=(2, 6))

        # Line Thickness
        ctk.CTkLabel(
            self.tab_local,
            text="Line Thickness:",
            font=ctk.CTkFont(size=12),
        ).pack(anchor="w")

        self.slider_thick = ctk.CTkSlider(
            self.tab_local,
            from_=1,
            to=4,
            number_of_steps=3,
            command=lambda val: self._apply_local_filter(),
        )
        self.slider_thick.set(2)
        self.slider_thick.pack(fill="x", pady=(2, 8))

        btn_apply_local = ctk.CTkButton(
            self.tab_local,
            text="⚡ Apply Local Filter Now",
            fg_color="#0284C7",
            hover_color="#0369A1",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._apply_local_filter,
        )
        btn_apply_local.pack(fill="x", pady=4)

    def _build_tab_import(self):
        ctk.CTkLabel(
            self.tab_import,
            text="Clean & Import Existing Image / Web Wireframe",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(anchor="w", pady=(6, 2))

        ctk.CTkLabel(
            self.tab_import,
            text="Drop or select any image (e.g. generated from Gemini Web Chat at gemini.google.com, screenshots, or Google images). "
                 "Automatically auto-crops whitespace borders, removes background, strictly binarizes to 1-bit thermal monochrome, and centers it.",
            font=ctk.CTkFont(size=11),
            text_color="gray70",
            wraplength=420,
            justify="left",
        ).pack(anchor="w", pady=(0, 8))

        btn_browse_import = ctk.CTkButton(
            self.tab_import,
            text="📂 Choose Image to Clean & Import...",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._browse_source_image,
        )
        btn_browse_import.pack(fill="x", pady=(0, 10))

        # Threshold slider for custom cleaning
        ctk.CTkLabel(
            self.tab_import,
            text="Binarization Threshold (Darkness Cutoff):",
            font=ctk.CTkFont(size=12),
        ).pack(anchor="w")

        self.slider_import_thresh = ctk.CTkSlider(
            self.tab_import,
            from_=60,
            to=240,
            number_of_steps=18,
            command=lambda val: self._apply_import_clean(),
        )
        self.slider_import_thresh.set(210)
        self.slider_import_thresh.pack(fill="x", pady=(2, 8))

        btn_clean = ctk.CTkButton(
            self.tab_import,
            text="⚡ Clean & Prepare for Thermal Printing",
            height=38,
            fg_color="#10B981",
            hover_color="#059669",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._apply_import_clean,
        )
        btn_clean.pack(fill="x", pady=4)

    def _set_local_preset(self, sens: int, thick: int):
        self.slider_sens.set(sens)
        self.slider_thick.set(thick)
        self._apply_local_filter()

    def _apply_import_clean(self):
        if not self.source_image:
            messagebox.showwarning("Missing Image", "Please select an image first.")
            return

        self.raw_unprocessed_image = self.source_image.copy()
        self._update_processed_preview()
        self.lbl_status.configure(text="Cleaned & prepared for thermal print!", text_color="#10B981")

    def _build_preview_panel(self, container):
        ctk.CTkLabel(
            container,
            text="Generated Icon Preview",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(anchor="w", padx=12, pady=(10, 4))

        # 256x256 Preview Box (White background with dark frame)
        self.preview_box = ctk.CTkFrame(
            container,
            width=260,
            height=260,
            fg_color="#FFFFFF",
            corner_radius=8,
            border_width=2,
            border_color="gray40",
        )
        self.preview_box.pack(padx=12, pady=6)
        self.preview_box.pack_propagate(False)

        self.lbl_preview_canvas = ctk.CTkLabel(
            self.preview_box,
            text="[ Generated wireframe\nwill appear here ]",
            text_color="gray40",
            font=ctk.CTkFont(size=12),
        )
        self.lbl_preview_canvas.pack(fill="both", expand=True)

        # Line Boldness Control for Thermal Printing
        bold_lbl = ctk.CTkLabel(
            container,
            text="Line Boldness (Thermal Label):",
            font=ctk.CTkFont(size=11, weight="bold"),
        )
        bold_lbl.pack(anchor="w", padx=12, pady=(4, 2))

        self.thickness_var = tk.StringVar(value="Bold")
        self.seg_thickness = ctk.CTkSegmentedButton(
            container,
            values=["Normal", "Bold", "Extra Bold", "Heavy"],
            variable=self.thickness_var,
            command=self._on_thickness_changed,
            height=28,
            font=ctk.CTkFont(size=11),
        )
        self.seg_thickness.pack(fill="x", padx=12, pady=(0, 4))

        # Status Label
        self.lbl_status = ctk.CTkLabel(
            container,
            text="Ready",
            font=ctk.CTkFont(size=12),
            text_color="gray60",
        )
        self.lbl_status.pack(pady=4)

        # Icon Name Entry
        ctk.CTkLabel(
            container,
            text="Icon Name / Part ID:",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(anchor="w", padx=12, pady=(4, 2))

        self.entry_icon_name = ctk.CTkEntry(
            container,
            placeholder_text="e.g. wago_221, m3_hex_screw",
            font=ctk.CTkFont(size=12),
        )
        self.entry_icon_name.pack(fill="x", padx=12, pady=(0, 8))

        # Save Button
        self.btn_save = ctk.CTkButton(
            container,
            text="💾 Save to Library & Use",
            height=38,
            fg_color="#10B981",
            hover_color="#059669",
            font=ctk.CTkFont(size=13, weight="bold"),
            state="disabled",
            command=self._save_and_use,
        )
        self.btn_save.pack(fill="x", padx=12, pady=(0, 6))

        btn_close = ctk.CTkButton(
            container,
            text="Close",
            fg_color="gray30",
            hover_color="gray40",
            command=self.destroy,
        )
        btn_close.pack(fill="x", padx=12)

    def _get_selected_thickness(self) -> int:
        val = self.thickness_var.get()
        if val == "Normal":
            return 1
        elif val == "Bold":
            return 2
        elif val == "Extra Bold":
            return 3
        elif val == "Heavy":
            return 4
        return 2

    def _on_thickness_changed(self, val=None):
        self._update_processed_preview()

    def _update_processed_preview(self):
        if not self.raw_unprocessed_image:
            return
        thick = self._get_selected_thickness()
        thresh = 210
        if hasattr(self, "slider_import_thresh"):
            try:
                thresh = int(self.slider_import_thresh.get())
            except Exception:
                pass
        try:
            processed = post_process_thermal(
                self.raw_unprocessed_image,
                binarize_threshold=thresh,
                line_thickness=thick,
            )
            self._display_result(processed)
        except Exception:
            pass

    def _browse_source_image(self):
        path = filedialog.askopenfilename(
            title="Select Component Photo",
            filetypes=[("Images", "*.png;*.jpg;*.jpeg;*.bmp;*.webp")],
        )
        if path and os.path.isfile(path):
            self.source_path = path
            self.lbl_source_filename.configure(text=os.path.basename(path))
            try:
                self.source_image = Image.open(path).convert("RGBA")
                # Update small thumbnail
                thumb = self.source_image.copy()
                thumb.thumbnail((140, 120), Image.Resampling.LANCZOS)
                self._ctk_source_thumb = ctk.CTkImage(
                    light_image=thumb, dark_image=thumb, size=thumb.size
                )
                self.lbl_source_thumb.configure(image=self._ctk_source_thumb, text="")

                # Auto-fill suggested name
                base_name = os.path.splitext(os.path.basename(path))[0].lower()
                clean_name = "".join(c if c.isalnum() else "_" for c in base_name).strip("_")
                self.entry_icon_name.delete(0, tk.END)
                self.entry_icon_name.insert(0, clean_name)

                # Auto-process if currently on Import or Offline Filter tab
                cur_tab = self.tabview.get()
                if "Clean & Import" in cur_tab:
                    self._apply_import_clean()
                elif "Offline Edge" in cur_tab:
                    self._apply_local_filter()
            except Exception as e:
                messagebox.showerror("Error Loading Photo", str(e))

    def _display_result(self, image: Image.Image):
        self.generated_image = image
        # Create thumbnail for 240x240 display inside white preview box
        preview_copy = image.copy()
        preview_copy.thumbnail((240, 240), Image.Resampling.LANCZOS)
        self._ctk_preview_img = ctk.CTkImage(
            light_image=preview_copy, dark_image=preview_copy, size=preview_copy.size
        )
        self.lbl_preview_canvas.configure(image=self._ctk_preview_img, text="")
        self.btn_save.configure(state="normal")

    def _generate_from_photo(self):
        if not self.source_image:
            messagebox.showwarning("Missing Photo", "Please select a component photo first.")
            return

        api_key = self.entry_api_key.get().strip()
        if not api_key:
            messagebox.showwarning(
                "Missing Gemini API Key",
                "Please enter your Google Gemini API Key below.\n\n"
                "You can get a free key from Google AI Studio (click 'Get Free Key ↗').\n"
                "Or use the 'Offline Edge Filter' tab without an API key.",
            )
            return

        self._set_loading(True, "Contacting Gemini API & generating wireframe...")
        details = self.entry_photo_details.get().strip()
        style = self.style_var.get()
        instructions = f"Style preference: {style}. {details}".strip()
        thick = self._get_selected_thickness()

        def worker():
            try:
                ai_generator.api_key = api_key
                raw_result = ai_generator.generate_from_image(
                    self.source_image,
                    custom_instructions=instructions,
                    line_thickness=thick,
                    return_raw=True,
                )
                self.after(0, lambda: self._on_generation_success(raw_result))
            except Exception as e:
                self.after(0, lambda err=str(e): self._on_generation_error(err))

        threading.Thread(target=worker, daemon=True).start()

    def _generate_from_text(self):
        prompt = self.entry_text_prompt.get("1.0", tk.END).strip()
        if not prompt:
            messagebox.showwarning("Missing Description", "Please enter a component description.")
            return

        api_key = self.entry_api_key.get().strip()
        if not api_key:
            messagebox.showwarning(
                "Missing API Key",
                "Please enter your Google Gemini API Key below.",
            )
            return

        self._set_loading(True, "Generating wireframe from description with Gemini...")
        thick = self._get_selected_thickness()

        def worker():
            try:
                ai_generator.api_key = api_key
                raw_result = ai_generator.generate_from_text(
                    prompt,
                    line_thickness=thick,
                    return_raw=True,
                )
                self.after(0, lambda: self._on_generation_success(raw_result))
            except Exception as e:
                self.after(0, lambda err=str(e): self._on_generation_error(err))

        threading.Thread(target=worker, daemon=True).start()

    def _apply_local_filter(self):
        if not self.source_image:
            messagebox.showwarning("Missing Photo", "Please select a photo first.")
            return

        sens = int(self.slider_sens.get())
        thick = int(self.slider_thick.get())

        self.lbl_status.configure(text="Processing local edge filter...", text_color="#38BDF8")
        try:
            # Generate offline line art from local filter
            result = local_edge_filter(self.source_image, sensitivity=sens, line_weight=thick, line_thickness=1)
            self.raw_unprocessed_image = result
            self._update_processed_preview()
            self.lbl_status.configure(text="Local filter applied successfully!", text_color="#10B981")
        except Exception as e:
            messagebox.showerror("Local Filter Error", str(e))

    def _set_loading(self, loading: bool, message: str = ""):
        self.is_generating = loading
        self.lbl_status.configure(text=message, text_color="#38BDF8" if loading else "gray60")
        state = "disabled" if loading else "normal"
        self.btn_gen_photo.configure(state=state)
        self.btn_gen_text.configure(state=state)

    def _on_generation_success(self, raw_result: Image.Image):
        self.raw_unprocessed_image = raw_result
        self._set_loading(False, "✨ Wireframe generated successfully!")
        self.lbl_status.configure(text="✨ AI Wireframe Generated!", text_color="#10B981")
        self._update_processed_preview()

    def _on_generation_error(self, err_msg: str):
        self._set_loading(False, f"Error: {err_msg[:80]}...")
        self.lbl_status.configure(text=f"Failed: {err_msg[:60]}", text_color="#EF4444")
        messagebox.showerror("Generation Error", f"Gemini generation error:\n\n{err_msg}")

    def _save_and_use(self):
        if not self.generated_image:
            return

        name = self.entry_icon_name.get().strip()
        if not name:
            name = "custom_wireframe"

        # Save to user icon directory
        saved_item = icon_manager.save_user_icon(self.generated_image, name)

        if self.on_save_callback:
            self.on_save_callback(saved_item.file_path)

        messagebox.showinfo(
            "Icon Saved",
            f"Icon saved successfully to your library as:\n{saved_item.title}\n\n"
            f"Path: {saved_item.file_path}",
        )
        self.destroy()
