#!/usr/bin/env python3
"""
Gemini icon generator for Cube Labeler.
Supports:
1. Gemini image-to-icon (photo of an object -> bold black-and-white icon)
2. Gemini text-to-icon (text description -> bold black-and-white icon)
3. Offline Local Edge Filter (PIL-based contour extraction with no API key)
4. Thermal post-processing (whitespace auto-trim, binarization, monochrome scaling)
The icon editor (core/icon_editor.py) does the clean-up of Gemini's pictures.
"""

import sys
import os
import io
import json
import base64
import urllib.request
import urllib.error
from typing import List, Optional, Tuple
from PIL import Image, ImageFilter, ImageOps

from core.config import config_manager

# System instruction prompt ensuring output is strictly thermal-print ready
THERMAL_WIREFRAME_SYSTEM_PROMPT = (
    "You are an expert icon designer making pictograms for a small thermal label printer (Brother PT-P300BT / P-Touch). "
    "The icon prints only about 56 dots high on 12 mm thermal label tape, so thin lines, small gaps and fine details disappear or blur together. "
    "\nCRITICAL DRAWING RULES:\n"
    "1. AGGRESSIVE SIMPLIFICATION & ABSTRACTION: Simplify and abstract the item freely so it is instantly readable on a small workshop label. "
    "Leave out reflections, glare, shadows, textures and small internal parts (springs, tiny screws, busbars). "
    "Keep the recognisable outer shape and the few features that identify the item (levers, ports, threads, slots, clips).\n"
    "2. BOLD & THICK LINEWORK: Every line, gap and feature must be bold and chunky, at least 1/20 of the icon's height. No hairlines or faint strokes.\n"
    "3. BACKGROUND: Pure solid white (#FFFFFF), nothing else in the picture.\n"
    "4. FOREGROUND: Pure solid black (#000000) only.\n"
    "5. NO GRADIENTS OR SHADING: No grey, no gradients, no hatching, no drop shadows. Only black and white.\n"
    "6. ONE ITEM, CENTRED: Draw a single item filling most of a square picture, with no text unless asked for.\n"
    "7. HIGH LEGIBILITY AT SMALL SIZES: The icon must stay recognisable when printed about 9 mm high."
)

# Drawing styles offered for Gemini; the first matches the built-in icon set
ICON_STYLES = {
    "Filled silhouette (like the built-in icons)": (
        "Draw it as a FILLED BLACK SILHOUETTE in a clean side or three-quarter view: solid black shapes, "
        "with the few identifying features cut out as bold white gaps."
    ),
    "Bold line drawing": (
        "Draw it as a BOLD BLACK LINE DRAWING: heavy, even outlines with no fill, like a simple technical pictogram."
    ),
    "Flat symbol": (
        "Draw it as a FLAT GEOMETRIC SYMBOL seen straight on, like a sign or a schematic symbol: simple solid shapes."
    ),
}
DEFAULT_STYLE = next(iter(ICON_STYLES))


def post_process_thermal(
    image: Image.Image,
    target_size: Tuple[int, int] = (256, 256),
    binarize_threshold: int = 210,
    line_thickness: int = 1,
    transparent_bg: bool = True,
    invert: bool = False,
) -> Image.Image:
    """
    Cleans, auto-crops, and strictly binarizes an image into pure monochrome
    optimized for thermal label printing.

    line_thickness:
      1 = Normal (original strokes preserved)
      2 = Bold (recommended for low-res thermal labels, 3x3 dilation)
      3 = Extra Bold (5x5 dilation)
      4 = Heavy / Chunky (7x7 dilation)
    invert:
      If True, explicitly inverts the image colors (black <-> white).
    """
    # 1. Flatten against white background
    if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
        bg = Image.new("RGBA", image.size, (255, 255, 255, 255))
        bg.paste(image, (0, 0), image.convert("RGBA"))
        gray = bg.convert("L")
    else:
        gray = image.convert("L")

    # 2. Check if image is inverted (predominantly dark background)
    corners = [
        gray.getpixel((0, 0)),
        gray.getpixel((gray.width - 1, 0)),
        gray.getpixel((0, gray.height - 1)),
        gray.getpixel((gray.width - 1, gray.height - 1)),
    ]
    if sum(corners) / 4.0 < 128:
        # Invert so background is white and drawing is black
        gray = ImageOps.invert(gray)

    # 2b. Explicit user-requested color inversion (reverse colors)
    if invert:
        gray = ImageOps.invert(gray)

    # 3. Auto-crop whitespace margins based on binarized threshold
    raw_mono = gray.point(lambda p: 0 if p < binarize_threshold else 255, mode="1").convert("L")
    inv = ImageOps.invert(raw_mono)
    bbox = inv.getbbox()
    if bbox:
        # Expand bbox by 2px margin so outer anti-aliasing is not clipped
        bx0 = max(0, bbox[0] - 2)
        by0 = max(0, bbox[1] - 2)
        bx1 = min(gray.width, bbox[2] + 2)
        by1 = min(gray.height, bbox[3] + 2)
        cropped = gray.crop((bx0, by0, bx1, by1))
    else:
        cropped = gray

    # 4. Scale into target_size with safe margins (~10% padding)
    cw, ch = target_size
    padding = int(min(cw, ch) * 0.10)
    avail_w = max(cw - padding * 2, 10)
    avail_h = max(ch - padding * 2, 10)

    aspect = cropped.width / cropped.height
    if aspect > (avail_w / avail_h):
        new_w = avail_w
        new_h = max(int(new_w / aspect), 1)
    else:
        new_h = avail_h
        new_w = max(int(new_h * aspect), 1)

    # Use LANCZOS antialiasing to prevent thin lines from skipping/fragmenting during downscaling
    scaled_gray = cropped.resize((new_w, new_h), Image.Resampling.LANCZOS)

    # 5. Strict binarization: pixels darker than threshold become 0 (black), rest 255 (white)
    mono = scaled_gray.point(lambda p: 0 if p < binarize_threshold else 255, mode="1").convert("L")

    # 6. Morphological line thickening / dilation for low-resolution thermal printing
    if line_thickness > 1:
        kernel_size = line_thickness * 2 - 1
        inv_mono = ImageOps.invert(mono)
        dilated_inv = inv_mono.filter(ImageFilter.MaxFilter(size=kernel_size))
        mono = ImageOps.invert(dilated_inv)

    # 7. Composite into final output canvas
    out_canvas = Image.new("RGBA", target_size, (255, 255, 255, 0 if transparent_bg else 255))
    paste_x = (cw - new_w) // 2
    paste_y = (ch - new_h) // 2

    # If transparent, make white pixels transparent and black pixels solid black
    if transparent_bg:
        scaled_rgba = Image.new("RGBA", (new_w, new_h), (0, 0, 0, 0))
        px_mono = mono.load()
        px_rgba = scaled_rgba.load()
        for y in range(new_h):
            for x in range(new_w):
                if px_mono[x, y] < 128:
                    px_rgba[x, y] = (0, 0, 0, 255)
        out_canvas.paste(scaled_rgba, (paste_x, paste_y), scaled_rgba)
    else:
        out_canvas.paste(mono, (paste_x, paste_y))

    return out_canvas


def local_edge_filter(
    image: Image.Image,
    sensitivity: int = 120,
    line_weight: int = 2,
    invert: bool = False,
    line_thickness: int = 1,
    **kwargs,
) -> Image.Image:
    """
    Offline local edge-detection and contour filter.
    Converts photos to clean monochrome line art without internet or API key.
    """
    # 1. Convert to grayscale and blur slightly to suppress noise
    gray = image.convert("L")
    blurred = gray.filter(ImageFilter.GaussianBlur(radius=1.2))

    # 2. Edge detection
    edges = blurred.filter(ImageFilter.FIND_EDGES)

    # 3. Enhance edge contrast and threshold
    # sensitivity 1-255: lower means more edges, higher means only strongest edges
    thresh = max(10, min(240, 255 - sensitivity))
    mono_edges = edges.point(lambda p: 255 if p > thresh else 0)

    # 4. Optional line dilation / thickening
    if line_weight > 1:
        mono_edges = mono_edges.filter(ImageFilter.MaxFilter(size=line_weight * 2 - 1))

    # Standard wireframe: black lines on white background
    if not invert:
        line_art = ImageOps.invert(mono_edges)
    else:
        line_art = mono_edges

    # Post process for thermal printing
    return post_process_thermal(line_art, line_thickness=line_thickness)


# Tried in order after the configured model, but only when a model does not exist (HTTP 404)
FALLBACK_IMAGE_MODELS = [
    "gemini-3.1-flash-image",
    "gemini-3.1-flash-lite-image",
    "gemini-2.5-flash-image",
    "gemini-3-pro-image",
]


class ModelNotFoundError(RuntimeError):
    """Raised when the requested Gemini model does not exist for this API key."""


class GeminiWireframeGenerator:
    """Client for Google Gemini & Imagen API to generate monochrome line art."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or config_manager.gemini_api_key

    def _call_gemini_rest(self, model: str, payload: dict) -> dict:
        key = self.api_key or config_manager.gemini_api_key
        if not key:
            raise ValueError("Gemini API key is not set. Please enter your API key in settings.")

        # The key goes in a header, never the URL, so it cannot leak through logs or proxies
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        data = json.dumps(payload).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "PrintLabel-Studio/2.0",
                "x-goog-api-key": key,
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            if e.code == 429 or "limit: 0" in err_body or "quota" in err_body.lower():
                msg = (
                    "Google AI Studio Quota Limit (Free Tier):\n"
                    "Google currently requires a billing account enabled on your AI Studio / Google Cloud project "
                    "for direct image-generation models (the free-tier quota for *-image models is set to 0 by Google).\n\n"
                    "Free alternative: make the picture in Gemini on the web (gemini.google.com), "
                    "save or copy it, then open or paste it in the icon editor."
                )
            else:
                try:
                    err_json = json.loads(err_body)
                    msg = err_json.get("error", {}).get("message", err_body)
                except Exception:
                    msg = err_body
            if e.code == 404:
                raise ModelNotFoundError(f"Gemini model '{model}' was not found: {msg}")
            raise RuntimeError(f"Gemini API Error ({e.code}): {msg}")
        except Exception as e:
            raise RuntimeError(f"Network error calling Gemini API: {e}")

    def generate_from_image(
        self,
        input_image: Image.Image,
        custom_instructions: str = "",
        model: Optional[str] = None,
        style: str = DEFAULT_STYLE,
        line_thickness: int = 1,
        return_raw: bool = False,
    ) -> Image.Image:
        """
        Takes a real-world photo, sends it to Gemini with our thermal icon prompt,
        and returns a post-processed pure monochrome icon.
        """
        # Compress / resize input image to reasonable size for API transfer (max 1024x1024)
        img_copy = input_image.convert("RGBA")
        img_copy.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
        # JPEG has no transparency; show see-through parts as white rather than black
        flat = Image.new("RGBA", img_copy.size, (255, 255, 255, 255))
        flat.alpha_composite(img_copy)
        buf = io.BytesIO()
        flat.convert("RGB").save(buf, format="JPEG", quality=85)
        b64_image = base64.b64encode(buf.getvalue()).decode("utf-8")

        prompt_text = (
            f"{THERMAL_WIREFRAME_SYSTEM_PROMPT}\n\n"
            "TASK: Make a label icon of the item shown in the attached photo.\n"
            f"STYLE: {ICON_STYLES.get(style, ICON_STYLES[DEFAULT_STYLE])}\n"
            "Ignore the photo's background, lighting and anything that is not the item itself.\n"
        )
        if custom_instructions.strip():
            prompt_text += f"Additional user specification: {custom_instructions.strip()}\n"

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt_text},
                        {
                            "inline_data": {
                                "mime_type": "image/jpeg",
                                "data": b64_image,
                            }
                        },
                    ]
                }
            ],
            "generationConfig": {
                "responseModalities": ["TEXT", "IMAGE"],
            },
        }

        return self._generate_image(payload, model, line_thickness, return_raw)

    def generate_from_text(
        self,
        prompt: str,
        model: Optional[str] = None,
        style: str = DEFAULT_STYLE,
        line_thickness: int = 1,
        return_raw: bool = False,
    ) -> Image.Image:
        """
        Generates an icon from a text description using Gemini image generation.
        """
        full_prompt = (
            f"{THERMAL_WIREFRAME_SYSTEM_PROMPT}\n\n"
            f"TASK: Make a label icon of: {prompt}.\n"
            f"STYLE: {ICON_STYLES.get(style, ICON_STYLES[DEFAULT_STYLE])}\n"
        )

        payload = {
            "contents": [{"parts": [{"text": full_prompt}]}],
            "generationConfig": {
                "responseModalities": ["TEXT", "IMAGE"],
            },
        }

        return self._generate_image(payload, model, line_thickness, return_raw)

    @staticmethod
    def _models_to_try(model: Optional[str]) -> List[str]:
        preferred = model or config_manager.gemini_model
        ordered = [preferred] + FALLBACK_IMAGE_MODELS
        return list(dict.fromkeys(m for m in ordered if m))

    def _generate_image(
        self, payload: dict, model: Optional[str], line_thickness: int, return_raw: bool
    ) -> Image.Image:
        """
        Calls the preferred model and returns its image. Falls back to the next model only
        when a model does not exist, so a real failure is never retried (and billed) again.
        """
        last_err: Optional[Exception] = None
        for m in self._models_to_try(model):
            try:
                res = self._call_gemini_rest(m, payload)
            except ModelNotFoundError as e:
                last_err = e
                continue

            candidates = res.get("candidates", [])
            if not candidates:
                raise RuntimeError(f"No candidate received from {m}.")

            parts = candidates[0].get("content", {}).get("parts", [])
            for part in parts:
                if "inlineData" in part:
                    img_bytes = base64.b64decode(part["inlineData"]["data"])
                    raw_result = Image.open(io.BytesIO(img_bytes))
                    if return_raw:
                        return raw_result
                    return post_process_thermal(raw_result, line_thickness=line_thickness)

            text_content = " ".join(p.get("text", "") for p in parts)
            raise RuntimeError(f"Model {m} returned text instead of an image: {text_content[:200]}")

        raise last_err or RuntimeError("Failed to generate wireframe image with Gemini.")


# Global generator instance
ai_generator = GeminiWireframeGenerator()
