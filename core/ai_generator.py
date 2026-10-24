#!/usr/bin/env python3
"""
AI icon redrawing for Cube Labeler.
Supports:
1. Redrawing a picture of an item as a bold black-and-white icon with Gemini, OpenAI or
   OpenRouter, using a ready-made preset or the user's own instructions
2. Offline Local Edge Filter (PIL-based contour extraction with no API key)
3. Thermal post-processing (whitespace auto-trim, binarization, monochrome scaling)
The icon editor (core/icon_editor.py) does the clean-up of the services' pictures.
"""

import sys
import os
import io
import json
import base64
import urllib.request
import urllib.error
import uuid
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from PIL import Image, ImageFilter, ImageOps

from core.config import DEFAULT_GEMINI_IMAGE_MODEL, config_manager
from core.icon_editor import DRAWING, SILHOUETTE

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

@dataclass(frozen=True)
class Preset:
    """A ready-made instruction for redrawing a picture, and how the editor first reads the result."""

    label: str
    instruction: str
    mode: str


# Ready-made redraws; the first matches the built-in icon set
PRESETS: List[Preset] = [
    Preset(
        "Filled silhouette (like the built-in icons)",
        "Draw it as a FILLED BLACK SILHOUETTE in a clean side or three-quarter view: solid black shapes, "
        "with the few identifying features cut out as bold white gaps.",
        SILHOUETTE,
    ),
    Preset(
        "Bold line drawing",
        "Draw it as a BOLD BLACK LINE DRAWING: heavy, even outlines with no fill, like a simple technical pictogram.",
        DRAWING,
    ),
    Preset(
        "Flat symbol",
        "Draw it as a FLAT GEOMETRIC SYMBOL seen straight on, like a sign or a schematic symbol: simple solid shapes.",
        SILHOUETTE,
    ),
    Preset(
        "Clean up, keep the shape",
        "Keep the item's own outline, view and proportions exactly as in the picture. Only clean it up: "
        "fill it solid black, drop the background, shading and small details, and make thin parts bold.",
        SILHOUETTE,
    ),
]
CUSTOM = "Custom"
PRESET_LABELS = [p.label for p in PRESETS] + [CUSTOM]
DEFAULT_PRESET = PRESETS[0].label


def preset_mode(label: str) -> str:
    """How the editor should first read a picture redrawn with this preset."""
    return next((p.mode for p in PRESETS if p.label == label), DRAWING)


def build_prompt(preset: str, custom: str = "") -> str:
    """The full instruction sent with the user's picture."""
    if preset == CUSTOM:
        if not custom.strip():
            raise ValueError("Type your own instructions for the Custom preset first.")
        style = custom.strip()
    else:
        style = next((p.instruction for p in PRESETS if p.label == preset), PRESETS[0].instruction)
    return (
        f"{THERMAL_WIREFRAME_SYSTEM_PROMPT}\n\n"
        "TASK: Make a label icon of the item shown in the attached picture.\n"
        f"STYLE: {style}\n"
        "Ignore the picture's background, lighting and anything that is not the item itself.\n"
    )


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


class ModelNotFoundError(RuntimeError):
    """Raised when the requested model does not exist for this API key."""


def _picture_bytes(picture: Image.Image, fmt: str = "PNG") -> bytes:
    """The picture shrunk to at most 1024 px, see-through parts shown as white, as PNG or JPEG."""
    img = picture.convert("RGBA")
    img.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
    flat = Image.new("RGBA", img.size, (255, 255, 255, 255))
    flat.alpha_composite(img)
    buf = io.BytesIO()
    if fmt == "JPEG":
        flat.convert("RGB").save(buf, format="JPEG", quality=85)
    else:
        flat.convert("RGB").save(buf, format="PNG")
    return buf.getvalue()


def _post(url: str, data: bytes, headers: Dict[str, str], service: str, timeout: int = 120) -> dict:
    """Sends a request and returns its JSON; errors carry the service's own message."""
    req = urllib.request.Request(url, data=data, headers={"User-Agent": "CubeLabeler", **headers}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            err = json.loads(body).get("error", {})
            msg = err.get("message", body) if isinstance(err, dict) else str(err)
        except Exception:
            msg = body
        raise _HttpError(e.code, body, f"{service} API error ({e.code}): {msg}")
    except Exception as e:
        raise RuntimeError(f"Network error calling {service}: {e}")


class _HttpError(RuntimeError):
    def __init__(self, code: int, body: str, message: str):
        super().__init__(message)
        self.code = code
        self.body = body


class ImageProvider:
    """An AI service that redraws a picture as an icon. Subclasses send the actual request."""

    id = ""
    name = ""
    key_url = ""
    key_note = ""
    default_model = ""
    # Tried in order after the chosen model, but only when a model does not exist (HTTP 404)
    fallback_models: List[str] = []

    def __init__(self, api_key: Optional[str] = None):
        self._api_key = api_key

    @property
    def api_key(self) -> str:
        return self._api_key or config_manager.api_key(self.id)

    @api_key.setter
    def api_key(self, value: str):
        self._api_key = value

    def models_to_try(self, model: Optional[str] = None) -> List[str]:
        preferred = model or config_manager.ai_model(self.id) or self.default_model
        return list(dict.fromkeys(m for m in [preferred] + self.fallback_models if m))

    def redraw(self, picture: Image.Image, preset: str = DEFAULT_PRESET, custom: str = "",
               model: Optional[str] = None) -> Image.Image:
        """Sends the picture with the preset's instruction and returns the service's picture, as is."""
        if not self.api_key:
            raise ValueError(f"{self.name} needs an API key. Add one under Settings in the main window.")
        prompt = build_prompt(preset, custom)
        last_err: Optional[Exception] = None
        for m in self.models_to_try(model):
            try:
                return self._redraw(picture, prompt, m)
            except ModelNotFoundError as e:
                last_err = e
        raise last_err or RuntimeError(f"{self.name} could not make the icon.")

    def _redraw(self, picture: Image.Image, prompt: str, model: str) -> Image.Image:
        req = self.request(picture, prompt, model)
        try:
            res = _post(req["url"], req["body"], {**req["headers"], **self.auth_headers(self.api_key)}, self.name)
        except _HttpError as e:
            raise self.http_error(e.code, e.body, str(e), model)
        return self.read_answer(res, model)

    # The pieces of a request, so the web version can send it from the browser itself

    def request(self, picture: Image.Image, prompt: str, model: str) -> Dict[str, object]:
        """The request for one model: {"url", "headers" (without the key), "body" as bytes}."""
        raise NotImplementedError

    def auth_headers(self, api_key: str) -> Dict[str, str]:
        return {"Authorization": f"Bearer {api_key}"}

    def read_answer(self, res: dict, model: str) -> Image.Image:
        """The picture in the service's answer."""
        return _picture_from_images_api(res, self.name)

    def http_error(self, code: int, body: str, message: str, model: str) -> Exception:
        """The error to raise for an HTTP error; ModelNotFoundError makes redraw try the next model."""
        if code == 404:
            return ModelNotFoundError(f"{self.name} model '{model}' was not found: {message}")
        return RuntimeError(message)


class GeminiProvider(ImageProvider):
    id = "gemini"
    name = "Gemini"
    key_url = "https://aistudio.google.com/app/apikey"
    key_note = ("Image generation needs billing enabled on your Google AI Studio project. "
                "Free alternative: make the picture at gemini.google.com and open or paste it in the editor.")
    default_model = DEFAULT_GEMINI_IMAGE_MODEL
    fallback_models = [
        "gemini-3.1-flash-image",
        "gemini-3.1-flash-lite-image",
        "gemini-2.5-flash-image",
        "gemini-3-pro-image",
    ]

    def models_to_try(self, model: Optional[str] = None) -> List[str]:
        preferred = model or config_manager.gemini_model
        return list(dict.fromkeys(m for m in [preferred] + self.fallback_models if m))

    def _call_gemini_rest(self, model: str, payload: dict) -> dict:
        # The key goes in a header, never the URL, so it cannot leak through logs or proxies
        try:
            return _post(self._url(model), json.dumps(payload).encode("utf-8"),
                         {"Content-Type": "application/json", **self.auth_headers(self.api_key)}, "Gemini")
        except _HttpError as e:
            raise self.http_error(e.code, e.body, str(e), model)

    @staticmethod
    def _url(model: str) -> str:
        return f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    def auth_headers(self, api_key: str) -> Dict[str, str]:
        return {"x-goog-api-key": api_key}

    def http_error(self, code: int, body: str, message: str, model: str) -> Exception:
        if code == 429 or "limit: 0" in body or "quota" in body.lower():
            return RuntimeError(
                "Google AI Studio Quota Limit (Free Tier):\n"
                "Google currently requires a billing account enabled on your AI Studio / Google Cloud project "
                "for direct image-generation models (the free-tier quota for *-image models is set to 0 by Google).\n\n"
                "Free alternative: make the picture in Gemini on the web (gemini.google.com), "
                "save or copy it, then open or paste it in the icon editor."
            )
        if code == 404:
            return ModelNotFoundError(f"Gemini model '{model}' was not found: {message}")
        return RuntimeError(message)

    @staticmethod
    def _payload(picture: Image.Image, prompt: str) -> dict:
        return {
            "contents": [{"parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": "image/jpeg",
                                 "data": base64.b64encode(_picture_bytes(picture, "JPEG")).decode("ascii")}},
            ]}],
            "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
        }

    def request(self, picture: Image.Image, prompt: str, model: str) -> Dict[str, object]:
        return {"url": self._url(model), "headers": {"Content-Type": "application/json"},
                "body": json.dumps(self._payload(picture, prompt)).encode("utf-8")}

    def _redraw(self, picture: Image.Image, prompt: str, model: str) -> Image.Image:
        return self.read_answer(self._call_gemini_rest(model, self._payload(picture, prompt)), model)

    def read_answer(self, res: dict, model: str) -> Image.Image:
        candidates = res.get("candidates", [])
        if not candidates:
            raise RuntimeError(f"No picture came back from {model}.")
        parts = candidates[0].get("content", {}).get("parts", [])
        for part in parts:
            if "inlineData" in part:
                return Image.open(io.BytesIO(base64.b64decode(part["inlineData"]["data"])))
        text = " ".join(p.get("text", "") for p in parts)
        raise RuntimeError(f"Model {model} returned text instead of a picture: {text[:200]}")


def _picture_from_images_api(res: dict, service: str) -> Image.Image:
    """Reads the picture from an OpenAI-style images response: data[0].b64_json."""
    data = res.get("data") or []
    if data and data[0].get("b64_json"):
        return Image.open(io.BytesIO(base64.b64decode(data[0]["b64_json"])))
    raise RuntimeError(f"No picture came back from {service}.")


class OpenAIProvider(ImageProvider):
    id = "openai"
    name = "OpenAI"
    key_url = "https://platform.openai.com/api-keys"
    key_note = "Uses the OpenAI Images API, billed to your OpenAI account."
    default_model = "gpt-image-2"
    fallback_models = ["gpt-image-1.5", "gpt-image-1"]

    def request(self, picture: Image.Image, prompt: str, model: str) -> Dict[str, object]:
        boundary = f"----CubeLabeler{uuid.uuid4().hex}"
        fields = [("model", model), ("prompt", prompt), ("size", "1024x1024")]
        body = io.BytesIO()
        for name, value in fields:
            body.write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n"
                       .encode("utf-8"))
        body.write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"image[]\"; filename=\"picture.png\"\r\n"
                   "Content-Type: image/png\r\n\r\n".encode("utf-8"))
        body.write(_picture_bytes(picture, "PNG"))
        body.write(f"\r\n--{boundary}--\r\n".encode("utf-8"))
        return {"url": "https://api.openai.com/v1/images/edits",
                "headers": {"Content-Type": f"multipart/form-data; boundary={boundary}"}, "body": body.getvalue()}

    def http_error(self, code: int, body: str, message: str, model: str) -> Exception:
        if code == 404 or "model_not_found" in body or "does not exist" in body:
            return ModelNotFoundError(f"OpenAI model '{model}' was not found: {message}")
        return RuntimeError(message)


class OpenRouterProvider(ImageProvider):
    id = "openrouter"
    name = "OpenRouter"
    key_url = "https://openrouter.ai/settings/keys"
    key_note = ("One key for image models from many companies, paid from your OpenRouter credits. "
                "Any image model that takes a picture works, e.g. openai/gpt-image-2.")
    default_model = "google/gemini-2.5-flash-image"

    def request(self, picture: Image.Image, prompt: str, model: str) -> Dict[str, object]:
        data_url = "data:image/png;base64," + base64.b64encode(_picture_bytes(picture, "PNG")).decode("ascii")
        payload = {
            "model": model,
            "prompt": prompt,
            "input_references": [{"type": "image_url", "image_url": {"url": data_url}}],
        }
        return {"url": "https://openrouter.ai/api/v1/images", "headers": {"Content-Type": "application/json"},
                "body": json.dumps(payload).encode("utf-8")}


PROVIDERS: Dict[str, ImageProvider] = {p.id: p for p in (GeminiProvider(), OpenAIProvider(), OpenRouterProvider())}


def current_provider() -> ImageProvider:
    """The service chosen under Settings."""
    return PROVIDERS.get(config_manager.ai_provider, PROVIDERS["gemini"])


def provider_by_name(name: str) -> Optional[ImageProvider]:
    return next((p for p in PROVIDERS.values() if p.name == name), None)
