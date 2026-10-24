"""
Python side of the Cube Labeler web app, loaded by Pyodide.

The page calls these functions to render labels and to build or read printer bytes;
JavaScript only moves those bytes over Web Serial. Everything here also runs on CPython,
which is how tests/test_web_bridge.py checks it.
"""

import dataclasses
import hashlib
import io
import os
import tempfile
from typing import Any, Dict, List, Optional

from core import protocol
from core.specs import TAPE_SPECS

USER_FONT_DIR = os.path.join(tempfile.gettempdir(), "cube-labeler-fonts")
IMAGE_DIR = os.path.join(tempfile.gettempdir(), "cube-labeler-images")

_renderer = None


def _get_renderer():
    """Imports the renderer (and Pillow) on first use, so the printer functions work without it."""
    global _renderer
    if _renderer is None:
        from core.label_renderer import LabelRenderer
        _renderer = LabelRenderer()
    return _renderer


def _to_bytes(data: Any) -> bytes:
    """Accepts Python bytes or a JavaScript Uint8Array proxy."""
    if hasattr(data, "to_bytes"):
        return data.to_bytes()
    return bytes(data)


def _to_dict(options: Any) -> Dict[str, Any]:
    """Accepts a dict or a JavaScript object proxy."""
    if hasattr(options, "to_py"):
        options = options.to_py()
    return dict(options or {})


def tape_widths():
    """Supported tape widths in mm, widest first."""
    return sorted(TAPE_SPECS, reverse=True)


def font_names():
    from core.font_manager import font_manager
    return font_manager.get_font_names()


def add_font(filename: str, data: Any) -> Optional[str]:
    """Stores an uploaded font file and returns its display name, or None if it isn't a font."""
    os.makedirs(USER_FONT_DIR, exist_ok=True)
    path = os.path.join(USER_FONT_DIR, os.path.basename(filename))
    with open(path, "wb") as f:
        f.write(_to_bytes(data))
    from PIL import ImageFont
    from core.font_manager import font_manager
    try:
        ImageFont.truetype(path, 10)
    except Exception:
        os.remove(path)
        return None
    return font_manager.register_custom_font(path)


def _image_path(data: Any) -> str:
    """Writes picture bytes to a file named by their hash (once) and returns its path."""
    raw = _to_bytes(data)
    os.makedirs(IMAGE_DIR, exist_ok=True)
    path = os.path.join(IMAGE_DIR, hashlib.sha1(raw).hexdigest())
    if not os.path.exists(path):
        with open(path, "wb") as f:
            f.write(raw)
    return path


def _png(image) -> bytes:
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


def _hide_cut_line(preview, config):
    """
    The preview of one label without its cut line, which only helps where labels meet in a
    strip; it is still printed, and the print dots view still shows it.
    """
    if not config.cut_line or preview.width < 3:
        return preview
    out = preview.copy()
    columns = []
    if config.cut_line_position in ("both", "start"):
        columns.append((0, 1))
    if config.cut_line_position in ("both", "end"):
        columns.append((out.width - 1, out.width - 2))
    for column, beside in columns:
        out.paste(preview.crop((beside, 0, beside + 1, out.height)), (column, 0))
    return out


def _known(cls, data: Dict[str, Any]) -> Dict[str, Any]:
    names = {f.name for f in dataclasses.fields(cls)}
    return {k: v for k, v in data.items() if k in names}


def _bin_config(data: Dict[str, Any]):
    """
    A bin label from the page: {"kind": "fastener" or "component", ...FastenerLabelConfig or
    ComponentLabelConfig fields}. Its own icon comes as bytes in icon_data; icon paths from
    the page are ignored.
    """
    from core.inventory_renderer import ComponentLabelConfig, FastenerLabelConfig
    data = dict(data)
    icon = data.pop("icon_data", None)
    if data.get("kind") == "component":
        fields = _known(ComponentLabelConfig, data)
        fields.pop("custom_icon_path", None)
        cfg = ComponentLabelConfig(**fields)
        if cfg.icon_type == "custom":
            cfg.custom_icon_path = _image_path(icon) if icon is not None else None
            if cfg.custom_icon_path is None:
                cfg.icon_type = "none"
    else:
        fields = _known(FastenerLabelConfig, data)
        fields.pop("custom_tool_icon_path", None)
        cfg = FastenerLabelConfig(**fields)
        if cfg.tool_type == "custom":
            cfg.custom_tool_icon_path = _image_path(icon) if icon is not None else None
            if cfg.custom_tool_icon_path is None:
                cfg.tool_type = "none"
    cfg.tape_width_mm = 12
    return cfg


def _label_config(options: Any):
    """
    LabelConfig from the page's options: LabelConfig field names (text, font_name,
    tape_width_mm, auto_fit_font, ...), a picture as bytes in image_data, and a bin label in
    "bin" (see _bin_config). Unknown keys are ignored.
    """
    from core.label_renderer import LabelConfig
    from core.specs import INVENTORY_TAPE_WIDTH_MM
    raw = _to_dict(options)
    opts = _known(LabelConfig, raw)
    opts.pop("image_path", None)
    opts.pop("inventory_config", None)
    if raw.get("image_data") is not None:
        opts["image_path"] = _image_path(raw["image_data"])
    if raw.get("bin") is not None:
        opts["inventory_config"] = _bin_config(raw["bin"])
        opts["tape_width_mm"] = INVENTORY_TAPE_WIDTH_MM
    return LabelConfig(**opts)


def _render_result(rendered) -> Dict[str, Any]:
    from PIL import ImageOps
    preview, raster_image, raster, metrics = rendered
    # The raster runs down the tape the way the printer feeds it; turn it back to read like the label
    dots = ImageOps.mirror(raster_image.convert("L")).rotate(90, expand=True)
    return {
        "preview_png": _png(preview),
        "dots_png": _png(ImageOps.invert(dots)),
        "raster": raster,
        "metrics": dataclasses.asdict(metrics),
    }


def render_label(options: Any) -> Dict[str, Any]:
    """
    Renders one label: a text label, or a bin label when options has "bin". Returns the
    preview PNG, the print dots as a PNG that reads like the preview, the print raster and
    the metrics.
    """
    config = _label_config(options)
    preview, *rest = _get_renderer().render(config)
    return _render_result((_hide_cut_line(preview, config), *rest))


def render_queue(labels: Any) -> Dict[str, Any]:
    """Renders queued labels as one strip with cut lines between them, like the desktop queue."""
    if hasattr(labels, "to_py"):
        labels = labels.to_py()
    configs = [_label_config(label) for label in labels]
    return _render_result(_get_renderer().render_batch(configs))


def label_thumbnail(options: Any, height: int = 48) -> bytes:
    """A small preview PNG of one label, for lists."""
    from PIL import Image
    preview = _get_renderer().render(_label_config(options))[0]
    width = max(1, round(preview.width * height / preview.height))
    return _png(preview.resize((width, int(height)), Image.Resampling.LANCZOS))


def bin_defaults(lang: str = "en") -> Dict[str, Any]:
    """The starting fastener and part labels (presets A2 and B1), in the label language."""
    from core.label_language import build_presets
    presets = build_presets(lang)
    fastener = dataclasses.asdict(presets["A2"].config)
    component = dataclasses.asdict(presets["B1"].config)
    fastener["kind"], component["kind"] = "fastener", "component"
    # The editor has one note line for a single bin (as on the desktop)
    fastener["standard_line1"], fastener["standard_line2"] = "", ""
    return {"fastener": fastener, "component": component}


def bin_name_suggestions(lang: str = "en") -> Dict[str, List[str]]:
    from core.label_language import component_categories, fastener_categories
    return {"fastener": fastener_categories(lang), "component": component_categories(lang)}


def label_languages() -> List[List[str]]:
    from core.label_language import LANGUAGES
    return [[code, name] for code, name in LANGUAGES.items()]


# --- Text editor helpers: the same styling rules as the desktop editor (core/rich_text.py) ---

def toggle_style(text: str, start: int, end: int, style: str) -> List[Any]:
    """Adds or removes bold, italic, underline or invert around text[start:end]: [text, start, end]."""
    from core import rich_text
    return list(rich_text.toggle_style(text, int(start), int(end), style))


def _line_span(text: str, start: int, end: int) -> range:
    first = text.count("\n", 0, int(start))
    last = text.count("\n", 0, int(end))
    return range(first, last + 1)


def restyle_lines(text: str, start: int, end: int, changes: Any) -> str:
    """
    Sets the size and/or alignment prefix of every line the selection touches. changes holds
    "size" ("large", "medium", "normal", "small") and/or "align" ("left", "center", "right",
    or None for the label's alignment).
    """
    from core import rich_text
    changes = _to_dict(changes)
    kwargs = {}
    if "size" in changes:
        kwargs["size"] = changes["size"]
    if "align" in changes:
        kwargs["align"] = changes["align"]
    lines = text.split("\n")
    for n in _line_span(text, start, end):
        lines[n] = rich_text.set_line_style(lines[n], **kwargs)
    return "\n".join(lines)


def line_style_at(text: str, pos: int) -> List[Any]:
    """The size and alignment of the line holding position pos: [size, align or None]."""
    from core import rich_text
    n = text.count("\n", 0, int(pos))
    return list(rich_text.line_style(text.split("\n")[n]))


def blank_raster(length_mm: float) -> bytes:
    """An empty raster that feeds length_mm of tape when printed (like the desktop's Feed tape)."""
    return bytes(protocol.LINE_BYTES * protocol.feed_dots(float(length_mm)))


def raster_lines(raster: Any) -> int:
    return protocol.validate_raster(_to_bytes(raster))


def status_query() -> bytes:
    """Bytes that reset the printer and ask for one 32-byte status packet."""
    return protocol.init_sequence() + protocol.status_request()


def reset_sequence() -> bytes:
    return protocol.init_sequence()


def print_command() -> bytes:
    return protocol.PRINT_COMMAND


def status_packet_size() -> int:
    return protocol.STATUS_PACKET_SIZE


def describe_status(raw: Any) -> Dict[str, Any]:
    """Decodes a status packet into plain values for the page."""
    status = protocol.parse_status(_to_bytes(raw))
    return {
        "model": status.model_name,
        "power": status.power_status,
        "errors": list(status.errors),
        "tape_width_mm": status.tape_width_mm,
        "tape_type": status.tape_type_name,
        "tape_color": status.bg_color_name,
        "text_color": status.fg_color_name,
        "phase": status.phase_name,
        "is_ready": status.is_ready,
        "tape_loaded": status.tape_loaded,
    }


def print_job(raw_status: Any, raster: Any, options: Any = None) -> bytes:
    """
    Checks the status packet read before printing, then returns the configuration and
    raster bytes for the job (send print_command() after them). Raises RuntimeError with
    a readable message if the printer isn't ready or has the wrong tape loaded.
    Options: auto_cut, end_margin, chaining, compress, required_tape_width_mm.
    """
    opts = _to_dict(options)
    status = protocol.parse_status(_to_bytes(raw_status))
    protocol.check_ready(status, opts.get("required_tape_width_mm"))

    data = _to_bytes(raster)
    lines = protocol.validate_raster(data)
    compress = bool(opts.get("compress", True))
    return protocol.job_configuration(
        lines,
        protocol.tape_dim(status),
        compress=compress,
        chaining=bool(opts.get("chaining", False)),
        auto_cut=bool(opts.get("auto_cut", False)),
        end_margin=int(opts.get("end_margin", 0)),
    ) + protocol.raster_lines(data, compress)


def completion_timeout(lines: int) -> float:
    return protocol.completion_timeout(lines)


def job_state(raw: Any) -> str:
    """
    Classifies a status packet read while printing: "completed", "pending" (phase change or
    notification) or "invalid" (not a status packet). Raises RuntimeError on a printer error.
    """
    try:
        status = protocol.parse_status(_to_bytes(raw))
    except ValueError:
        return "invalid"
    protocol.raise_if_error(status)
    return "completed" if protocol.is_completed(status) else "pending"


# --- Icons: the same steps as the desktop icon library and editor (core/icon_editor.py) ---

def _open_picture(data: Any):
    from PIL import Image, ImageOps
    with Image.open(io.BytesIO(_to_bytes(data))) as src:
        # Phone photos carry their rotation in EXIF
        return ImageOps.exif_transpose(src).convert("RGBA")


def icon_print_preview(data: Any, dots: int = 56) -> bytes:
    """An icon as it comes out on a 12 mm bin label: cropped to its ink, shrunk, black and white."""
    from core.icon_editor import print_dots
    return _png(print_dots(_open_picture(data), int(dots)))


def make_icon(data: Any, edit: Any = None, touch: Any = None) -> Dict[str, Any]:
    """
    Turns a picture into a black-and-white icon with the editor's settings (defaults when
    edit is None). Returns the icon PNG, the original as it is kept with the icon, the
    settings used, and whether the icon has any ink.
    """
    from PIL import Image
    from core.icon_editor import IconEdit, has_ink, ink_mask, apply_touch, mask_to_icon, prepare_original
    original = prepare_original(_open_picture(data))
    settings = IconEdit.from_dict(_to_dict(edit) if edit is not None else None)
    touch_layer = None
    if touch is not None:
        with Image.open(io.BytesIO(_to_bytes(touch))) as src:
            touch_layer = src.convert("L")
    mask = apply_touch(ink_mask(original, settings), touch_layer)
    return {
        "icon_png": _png(mask_to_icon(mask)),
        "original_png": _png(original),
        "edit": settings.to_dict(),
        "has_ink": has_ink(mask),
    }
