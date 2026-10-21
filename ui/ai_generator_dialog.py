#!/usr/bin/env python3
"""
"Make an icon" dialog for Cube Labeler.
Provides:
1. Clean and import: tidy up an existing image for thermal printing (free, offline)
2. From a photo: line-art from a photo using Gemini
3. From a description: line-art from a text description using Gemini
4. Save directly into the user icon library and use it on the label
"""

import os
import sys
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Callable, Optional
import customtkinter as ctk
from PIL import Image

from core.config import config_manager
from core.ai_generator import (
    ai_generator,
    post_process_thermal,
    THERMAL_WIREFRAME_SYSTEM_PROMPT,
)
from core.icon_manager import icon_manager

TAB_IMPORT = "Clean and import"
TAB_PHOTO = "From a photo"
TAB_TEXT = "From a description"

# Line thickness choices and the stroke width each one adds
THICKNESS = {"Normal": 1, "Bold": 2, "Extra bold": 3, "Heavy": 4}

MUTED = ("gray40", "gray60")
PREVIEW_BOX = 220
OK_GREEN = "#10B981"
BUSY_BLUE = "#38BDF8"
ERROR_RED = "#EF4444"


class AIGeneratorDialog(ctk.CTkToplevel):
    """Modal dialog for generating thermal wireframe icons using Gemini AI or cleaning web icons."""

    def __init__(self, parent, on_save_callback: Optional[Callable[[str], None]] = None):
        super().__init__(parent)
        self.on_save_callback = on_save_callback

        self.title("Make an icon")
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
            text="Make an icon",
            font=ctk.CTkFont(size=18, weight="bold"),
        )
        title_lbl.pack(anchor="w")

        desc_lbl = ctk.CTkLabel(
            header,
            text="Turn an image, a photo or a description into a black-and-white icon for the label.",
            font=ctk.CTkFont(size=12),
            text_color=MUTED,
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

        # The free, offline option comes first; the Gemini tabs need an API key
        self.tab_import = self.tabview.add(TAB_IMPORT)
        self.tab_photo = self.tabview.add(TAB_PHOTO)
        self.tab_text = self.tabview.add(TAB_TEXT)

        self._build_tab_import()
        self._build_tab_photo()
        self._build_tab_text()
        self.tabview.set(TAB_IMPORT)

        # The Gemini key lives in Settings; just say whether it's set
        key_note = (
            "Gemini options use the API key saved in Settings."
            if config_manager.gemini_api_key
            else "Gemini options need an API key. Add one in Settings in the main window."
        )
        self.lbl_key_note = ctk.CTkLabel(
            left_frame, text=key_note, anchor="w", text_color=MUTED, font=ctk.CTkFont(size=11)
        )
        self.lbl_key_note.pack(fill="x", padx=12, pady=(0, 8))

        # --- Right Side: Preview & Save ---
        self._build_preview_panel(right_frame)


    def _build_tab_photo(self):
        # 1. Source Image Picker
        picker_frame = ctk.CTkFrame(self.tab_photo, fg_color="transparent")
        picker_frame.pack(fill="x", pady=6)

        btn_browse = ctk.CTkButton(
            picker_frame,
            text="Choose photo…",
            command=self._browse_source_image,
        )
        btn_browse.pack(side="left", padx=(0, 8))

        self.lbl_source_filename = ctk.CTkLabel(
            picker_frame,
            text="No photo selected",
            font=ctk.CTkFont(size=12),
            text_color=MUTED,
        )
        self.lbl_source_filename.pack(side="left")

        # Thumbnail display of source photo
        self.lbl_source_thumb = ctk.CTkLabel(
            self.tab_photo,
            text="No photo",
            text_color=MUTED,
            width=140,
            height=120,
            fg_color=("gray85", "gray15"),
            corner_radius=6,
        )
        self.lbl_source_thumb.pack(pady=4)

        # Prompt / Style
        ctk.CTkLabel(
            self.tab_photo,
            text="Style",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(anchor="w", pady=(6, 2))

        self.style_var = tk.StringVar(value="Isometric technical wireframe (recommended)")
        self.combo_style = ctk.CTkComboBox(
            self.tab_photo,
            values=[
                "Isometric technical wireframe (recommended)",
                "Top-down blueprint outline",
                "Monochrome silhouette",
                "Schematic vector symbol",
            ],
            variable=self.style_var,
        )
        self.combo_style.pack(fill="x", pady=(0, 6))

        ctk.CTkLabel(
            self.tab_photo,
            text="Extra details (optional)",
            font=ctk.CTkFont(size=12),
        ).pack(anchor="w", pady=(2, 2))

        self.entry_photo_details = ctk.CTkEntry(
            self.tab_photo,
            placeholder_text="e.g. emphasize lever clips, 3 ports, DIN markings",
            font=ctk.CTkFont(size=12),
        )
        self.entry_photo_details.pack(fill="x", pady=(0, 10))

        # Billing note
        ctk.CTkLabel(
            self.tab_photo,
            text="Gemini image generation needs billing turned on in Google AI Studio. "
                 "For a free option, make the image in Gemini on the web (gemini.google.com) "
                 f"and bring it in with {TAB_IMPORT}.",
            font=ctk.CTkFont(size=11),
            text_color=MUTED,
            wraplength=420,
            justify="left",
            anchor="w",
        ).pack(fill="x", pady=(4, 6))

        # Generate Button
        self.btn_gen_photo = ctk.CTkButton(
            self.tab_photo,
            text="Generate with Gemini",
            height=36,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._generate_from_photo,
        )
        self.btn_gen_photo.pack(fill="x", pady=4)

    def _build_tab_text(self):
        ctk.CTkLabel(
            self.tab_text,
            text="Describe the part or tool",
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
            text="For example: M3 nylon lock nut, NEMA 17 stepper motor, USB-C socket, rotary encoder",
            font=ctk.CTkFont(size=11),
            text_color=MUTED,
            wraplength=420,
            justify="left",
        ).pack(anchor="w", pady=(0, 12))

        self.btn_gen_text = ctk.CTkButton(
            self.tab_text,
            text="Generate with Gemini",
            height=36,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._generate_from_text,
        )
        self.btn_gen_text.pack(fill="x", pady=4)

    def _build_tab_import(self):
        ctk.CTkLabel(
            self.tab_import,
            text="Use an image you already have",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(anchor="w", pady=(6, 2))

        ctk.CTkLabel(
            self.tab_import,
            text="Pick any image, such as one made in Gemini on the web, a screenshot or a downloaded icon. "
                 "It is cropped to its content, the background is removed, and it is turned into "
                 "pure black and white for the printer. Free and works offline.",
            font=ctk.CTkFont(size=11),
            text_color=MUTED,
            wraplength=420,
            justify="left",
        ).pack(anchor="w", pady=(0, 8))

        btn_browse_import = ctk.CTkButton(
            self.tab_import,
            text="Choose image…",
            height=36,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._browse_source_image,
        )
        btn_browse_import.pack(fill="x", pady=(0, 4))

        self.lbl_import_filename = ctk.CTkLabel(
            self.tab_import,
            text="No image selected",
            font=ctk.CTkFont(size=12),
            text_color=MUTED,
        )
        self.lbl_import_filename.pack(fill="x", pady=(0, 10))

        # Threshold slider for custom cleaning
        ctk.CTkLabel(
            self.tab_import,
            text="Darkness cutoff",
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
        self.slider_import_thresh.pack(fill="x", pady=(2, 10))

        # Swap black and white
        self.btn_invert = ctk.CTkButton(
            self.tab_import,
            text="Swap black and white",
            fg_color="gray40",
            hover_color="gray30",
            command=self._toggle_invert,
        )
        self.btn_invert.pack(fill="x", pady=(4, 6))

    def _flash_preview_box(self):
        try:
            self.preview_box.configure(border_color=OK_GREEN, border_width=3)
            self.after(500, lambda: self.preview_box.configure(border_color="gray40", border_width=2))
        except Exception:
            pass

    def _toggle_invert(self):
        if not self.source_image:
            self._browse_source_image()
            return
        self.invert_colors = not getattr(self, "invert_colors", False)
        self._update_processed_preview()
        self._flash_preview_box()
        state = "Black and white swapped" if self.invert_colors else "Black and white as in the image"
        self.lbl_status.configure(text=state, text_color=MUTED)

    def _apply_import_clean(self):
        if not self.source_image:
            return

        self.raw_unprocessed_image = self.source_image.copy()
        self._update_processed_preview()
        self.lbl_status.configure(text="Image cleaned up for printing", text_color=OK_GREEN)

    def _build_preview_panel(self, container):
        # Packed from the bottom first so Save and Close stay visible when the dialog is small
        btn_close = ctk.CTkButton(
            container,
            text="Close",
            fg_color="gray40",
            hover_color="gray30",
            command=self.destroy,
        )
        btn_close.pack(side="bottom", fill="x", padx=12, pady=(0, 12))

        self.btn_save = ctk.CTkButton(
            container,
            text="Save and use",
            height=36,
            font=ctk.CTkFont(size=13, weight="bold"),
            state="disabled",
            command=self._save_and_use,
        )
        self.btn_save.pack(side="bottom", fill="x", padx=12, pady=(0, 6))

        self.entry_icon_name = ctk.CTkEntry(
            container,
            placeholder_text="e.g. wago_221, m3_hex_screw",
            font=ctk.CTkFont(size=12),
        )
        self.entry_icon_name.pack(side="bottom", fill="x", padx=12, pady=(0, 8))

        ctk.CTkLabel(
            container,
            text="Icon name",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(side="bottom", anchor="w", padx=12, pady=(4, 2))

        ctk.CTkLabel(
            container,
            text="Preview",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(anchor="w", padx=12, pady=(10, 4))

        # White preview box, like the tape
        self.preview_box = ctk.CTkFrame(
            container,
            width=PREVIEW_BOX,
            height=PREVIEW_BOX,
            fg_color="#FFFFFF",
            corner_radius=8,
            border_width=2,
            border_color="gray40",
        )
        self.preview_box.pack(padx=12, pady=6)
        self.preview_box.pack_propagate(False)

        self.lbl_preview_canvas = ctk.CTkLabel(
            self.preview_box,
            text="The icon will appear here",
            text_color="gray40",
            font=ctk.CTkFont(size=12),
        )
        self.lbl_preview_canvas.pack(fill="both", expand=True)

        # Line thickness on the printed label
        bold_lbl = ctk.CTkLabel(
            container,
            text="Line thickness",
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        bold_lbl.pack(anchor="w", padx=12, pady=(4, 2))

        self.thickness_var = tk.StringVar(value="Normal")
        self.seg_thickness = ctk.CTkSegmentedButton(
            container,
            values=list(THICKNESS),
            variable=self.thickness_var,
            command=self._on_thickness_changed,
            height=28,
            font=ctk.CTkFont(size=11),
        )
        self.seg_thickness.pack(fill="x", padx=12, pady=(0, 4))

        # Status Label
        self.lbl_status = ctk.CTkLabel(
            container,
            text="",
            font=ctk.CTkFont(size=12),
            text_color=MUTED,
            wraplength=PREVIEW_BOX,
        )
        self.lbl_status.pack(padx=12, pady=4)

    def _get_selected_thickness(self) -> int:
        return THICKNESS.get(self.thickness_var.get(), 1)

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
        invert = getattr(self, "invert_colors", False)
        try:
            processed = post_process_thermal(
                self.raw_unprocessed_image,
                binarize_threshold=thresh,
                line_thickness=thick,
                invert=invert,
            )
            self._display_result(processed)
        except Exception as e:
            print(f"[AIGeneratorDialog] Error during post_process_thermal: {e}")

    def _browse_source_image(self):
        path = filedialog.askopenfilename(
            parent=self,
            title="Choose an image",
            filetypes=[("Images", "*.png;*.jpg;*.jpeg;*.bmp;*.webp")],
        )
        if path and os.path.isfile(path):
            self.source_path = path
            self.invert_colors = False
            self.lbl_source_filename.configure(text=os.path.basename(path))
            if hasattr(self, "lbl_import_filename"):
                self.lbl_import_filename.configure(
                    text=os.path.basename(path),
                    text_color=("gray10", "gray90"),
                )
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

                # Clean it up straight away when on the import tab
                if self.tabview.get() == TAB_IMPORT:
                    self._apply_import_clean()
            except Exception as e:
                messagebox.showerror("Could not open the image", str(e), parent=self)

    def _display_result(self, image: Image.Image):
        self.generated_image = image
        # Thumbnail that fits inside the white preview box
        preview_copy = image.copy()
        size = PREVIEW_BOX - 20
        preview_copy.thumbnail((size, size), Image.Resampling.LANCZOS)
        self._ctk_preview_img = ctk.CTkImage(
            light_image=preview_copy, dark_image=preview_copy, size=preview_copy.size
        )
        self.lbl_preview_canvas.configure(image=self._ctk_preview_img, text="")
        self.btn_save.configure(state="normal")

    def _generate_from_photo(self):
        if not self.source_image:
            messagebox.showwarning("Choose a photo", "Choose a photo of the part first.", parent=self)
            return

        api_key = self._api_key_or_warn()
        if not api_key:
            return

        self._set_loading(True, "Asking Gemini for an icon…")
        details = self.entry_photo_details.get().strip()
        style = self.style_var.get()
        instructions = f"Style preference: {style}. {details}".strip()
        thick = self._get_selected_thickness()

        ai_generator.api_key = api_key
        source = self.source_image
        self._run_generation(
            lambda: ai_generator.generate_from_image(
                source,
                custom_instructions=instructions,
                line_thickness=thick,
                return_raw=True,
            )
        )

    def _generate_from_text(self):
        prompt = self.entry_text_prompt.get("1.0", tk.END).strip()
        if not prompt:
            messagebox.showwarning("Add a description", "Describe the part or tool first.", parent=self)
            return

        api_key = self._api_key_or_warn()
        if not api_key:
            return

        self._set_loading(True, "Asking Gemini for an icon…")
        thick = self._get_selected_thickness()

        ai_generator.api_key = api_key
        self._run_generation(
            lambda: ai_generator.generate_from_text(
                prompt,
                line_thickness=thick,
                return_raw=True,
            )
        )

    def _api_key_or_warn(self) -> str:
        key = config_manager.gemini_api_key
        if not key:
            messagebox.showwarning(
                "Add a Gemini API key",
                "Gemini needs an API key. Add one under Settings in the main window.\n\n"
                f"Or make the image in Gemini on the web and bring it in with {TAB_IMPORT}.",
                parent=self,
            )
        return key

    def _run_generation(self, generate: Callable[[], Image.Image]):
        """
        Runs a Gemini call on a worker thread. Tkinter is not thread-safe, so the worker only
        puts its result on a queue and the Tk main loop polls it.
        """
        results: "queue.Queue" = queue.Queue()

        def worker():
            try:
                results.put((True, generate()))
            except Exception as e:
                results.put((False, str(e)))

        def poll():
            if not self.winfo_exists():
                return
            try:
                ok, value = results.get_nowait()
            except queue.Empty:
                self.after(100, poll)
                return
            if ok:
                self._on_generation_success(value)
            else:
                self._on_generation_error(value)

        threading.Thread(target=worker, daemon=True).start()
        self.after(100, poll)

    def _set_loading(self, loading: bool, message: str = ""):
        self.is_generating = loading
        self.lbl_status.configure(text=message, text_color=BUSY_BLUE if loading else MUTED)
        state = "disabled" if loading else "normal"
        self.btn_gen_photo.configure(state=state)
        self.btn_gen_text.configure(state=state)

    def _on_generation_success(self, raw_result: Image.Image):
        self.raw_unprocessed_image = raw_result
        self._set_loading(False)
        self.lbl_status.configure(text="Icon ready", text_color=OK_GREEN)
        self._update_processed_preview()
        self._flash_preview_box()

    def _on_generation_error(self, err_msg: str):
        self._set_loading(False)
        self.lbl_status.configure(text="Gemini could not make the icon", text_color=ERROR_RED)
        messagebox.showerror("Gemini could not make the icon", err_msg, parent=self)

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
            "Icon saved",
            f"Saved to your icon library as {saved_item.title}.\n\n{saved_item.file_path}",
            parent=self,
        )
        self.destroy()
