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
from typing import Any, Dict, List, Optional, Tuple

from core import protocol
from core.specs import TAPE_SPECS

USER_FONT_DIR = os.path.join(tempfile.gettempdir(), "cube-labeler-fonts")
IMAGE_DIR = os.path.join(tempfile.gettempdir(), "cube-labeler-images")

_renderer = None

# Bin labels use Arial Bold on the desktop; here Arimo Medium, unless Settings picks another
WEB_BIN_FONT = "Arimo Medium"
WEIGHT_NAMES = (" Regular", " Medium", " SemiBold", " Light", " ExtraLight", " Thin", " ExtraBold", " Black")


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


def font_file(name: str) -> Optional[bytes]:
    """The file of a font from font_names(), for showing it in the page's font menus."""
    from core.font_manager import font_manager
    if name not in font_names():
        return None
    with open(font_manager.resolve_font_path(name), "rb") as f:
        return f.read()


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


def bold_font(name: str, names: List[str]) -> str:
    """The bold font of name's family ("Arimo Medium" -> "Arimo Bold"), or name if it has none."""
    if name.endswith(" Bold"):
        return name
    family = next((name[:-len(w)] for w in WEIGHT_NAMES if name.endswith(w)), name)
    return family + " Bold" if family + " Bold" in names else name


def _bin_fonts(name: Any, bold_name: Any = True) -> Tuple[str, str]:
    """
    The fonts for a bin label: the font from Settings, or the default one if it isn't here
    (anymore), and for the name (SCREWS, BEARINGS) that font's bold unless bold_name is off.
    """
    names = font_names()
    font = name if name in names else WEB_BIN_FONT
    return font, bold_font(font, names) if bold_name is not False else font


def _label_config(options: Any):
    """
    LabelConfig from the page's options: LabelConfig field names (text, font_name,
    tape_width_mm, auto_fit_font, ...), a picture as bytes in image_data, and a bin label in
    "bin" (see _bin_config) with its font from Settings in "bin_font" and "bin_bold_name".
    Unknown keys are ignored.
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
        inv = _bin_config(raw["bin"])
        inv.font_name, inv.name_font_name = _bin_fonts(raw.get("bin_font"), raw.get("bin_bold_name", True))
        opts["inventory_config"] = inv
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


def render_queue(labels: Any, copies: Any = None) -> Dict[str, Any]:
    """
    Renders queued labels as one strip with cut lines between them, like the desktop queue.
    copies[i] prints labels[i] that many times in a row. "spans" holds each printed label's
    [start, end] as a share of the strip's width, for pointing at it in the preview.
    """
    if hasattr(labels, "to_py"):
        labels = labels.to_py()
    if hasattr(copies, "to_py"):
        copies = copies.to_py()
    configs = []
    for i, label in enumerate(labels):
        config = _label_config(label)
        configs += [config] * max(1, int(copies[i]) if copies else 1)
    spans: List[Any] = []
    rendered = _get_renderer().render_batch(configs, spans=spans)
    result = _render_result(rendered)
    width = rendered[0].width
    result["spans"] = [[start / width, end / width] for start, end in spans]
    return result


def queue_lengths(labels: Any) -> Dict[str, Any]:
    """
    The widths of queued labels (one entry per queue item, copies not repeated), for working
    out how much tape a part of the queue uses without drawing it. See
    LabelRenderer.tape_lengths.
    """
    if hasattr(labels, "to_py"):
        labels = labels.to_py()
    return _get_renderer().tape_lengths([_label_config(label) for label in labels])


def border_tiles(tape_width_mm: float = 12.0, font_name: str = "Arimo") -> List[Dict[str, Any]]:
    """
    Every border for the picker, in order: id, name, category and a PNG of a short sample
    label with it, drawn like the print (see core/borders.py).
    """
    from PIL import Image
    from core import borders
    from core.label_renderer import LabelConfig
    renderer = _get_renderer()
    tiles = []
    for border in borders.BORDERS_LIST:
        if border.id == "none":
            continue
        config = LabelConfig(text="Abc", font_name=font_name, tape_width_mm=float(tape_width_mm),
                             frame=border.id, cut_line=False, font_scale=75.0)
        # The sample text is kept smaller than Fit, so it stands clear of every border
        label = renderer.render(config)[0]
        # Every tile the same size and scale, the label in the middle
        width = max(label.width, round(label.height * 40 / 13))
        preview = Image.new("RGB", (width, label.height), "white")
        preview.paste(label, ((width - label.width) // 2, 0))
        tiles.append({"id": border.id, "name": border.name, "category": border.category, "png": _png(preview)})
    return tiles


def border_categories() -> List[List[str]]:
    from core import borders
    return [list(c) for c in borders.CATEGORIES]


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


def qr_fit(data: str, tape_width_mm: float, scale: float = 1.0) -> Dict[str, Any]:
    """
    How a QR code of data prints on the tape: its squares across (with the border) and the
    printer dots each square gets. Under about 2 dots a square, phones struggle to read it.
    """
    import qrcode
    from core.specs import get_tape_spec
    if not str(data).strip():
        return {"modules": 0, "dots": 0, "dots_per_module": 0}
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=1, border=1)
    qr.add_data(str(data))
    qr.make(fit=True)
    modules = qr.modules_count + 2
    dots = max(int(get_tape_spec(float(tape_width_mm))["printable_height"] * float(scale)), 8)
    return {"modules": modules, "dots": dots, "dots_per_module": round(dots / modules, 2)}


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


# The icon editor calls edit_icon on every change, so the picture and the last masks are kept
_EDIT_SOURCES: Dict[str, Any] = {}
_EDIT_MASKS: Dict[Any, Any] = {}


def _remember(cache: Dict[Any, Any], key: Any, value: Any, keep: int) -> Any:
    cache.pop(key, None)
    cache[key] = value
    while len(cache) > keep:
        cache.pop(next(iter(cache)))
    return value


def _touch_layer(touch: Any):
    """Touch-ups as the editor's grid: raw cells from the page, or a PNG from a desktop backup."""
    from PIL import Image
    from core.icon_editor import TOUCH_GRID
    if touch is None:
        return None
    data = _to_bytes(touch)
    if len(data) == TOUCH_GRID * TOUCH_GRID:
        return Image.frombytes("L", (TOUCH_GRID, TOUCH_GRID), data)
    with Image.open(io.BytesIO(data)) as src:
        layer = src.convert("L")
    return layer if layer.size == (TOUCH_GRID, TOUCH_GRID) else None


def touch_cells(touch: Any) -> Optional[bytes]:
    """Touch-ups as raw grid cells (one byte each), from either form edit_icon takes."""
    layer = _touch_layer(touch)
    return layer.tobytes() if layer is not None else None


def touch_png(cells: Any) -> Optional[bytes]:
    """Raw touch-up cells as the PNG the desktop app keeps next to an icon."""
    layer = _touch_layer(cells)
    return _png(layer) if layer is not None else None


def prepare_icon_original(data: Any) -> bytes:
    """A picture as it is kept with an icon: upright, at most 1024 pixels across, PNG."""
    from core.icon_editor import prepare_original
    return _png(prepare_original(_open_picture(data)))


def edit_icon(original: Any, edit: Any = None, touch: Any = None, view: int = 480) -> Dict[str, Any]:
    """
    Everything the icon editor shows for a picture and its settings:
    base_png, the icon before touch-ups (the page draws touch-ups over it while you draw),
    icon_png with touch-ups as it is saved, print_png as it prints on a
    12 mm bin label, the darkness cutoff used, whether there is any ink, the settings as
    read, and view_png, the picture turned and mirrored the way the crop box refers to it.
    """
    from core.icon_editor import (
        IconEdit, apply_touch, has_ink, ink_mask, mask_to_icon, orient, print_dots, threshold_for,
    )
    data = _to_bytes(original)
    digest = hashlib.sha1(data).hexdigest()
    source = _EDIT_SOURCES.get(digest)
    if source is None:
        source = _open_picture(data)
    _remember(_EDIT_SOURCES, digest, source, 2)

    settings = IconEdit.from_dict(_to_dict(edit) if edit is not None else None)
    key = (digest, repr(sorted(settings.to_dict().items())))
    cached = _EDIT_MASKS.get(key)
    if cached is None:
        cached = (ink_mask(source, settings), threshold_for(source, settings))
    _remember(_EDIT_MASKS, key, cached, 6)
    mask, threshold = cached

    full = apply_touch(mask, _touch_layer(touch))
    icon = mask_to_icon(full)
    oriented = orient(source, settings).copy()
    oriented.thumbnail((int(view), int(view)))
    return {
        "base_png": _png(mask_to_icon(mask)),
        "icon_png": _png(icon),
        "print_png": _png(print_dots(icon)) if has_ink(full) else None,
        "threshold": threshold,
        "has_ink": has_ink(full),
        "edit": settings.to_dict(),
        "view_png": _png(oriented),
    }


# --- Templates: the desktop app's template files, read and written by the web version ---

# Fonts the web version ships in place of Windows fonts that templates name
WEB_FONT_SUBSTITUTES = {
    "Consolas": "JetBrains Mono",
    "Courier New": "JetBrains Mono",
    "Segoe UI": "Inter",
    "Verdana": "Inter",
    "Tahoma": "Inter",
    "Comic Sans MS": "Comic Neue",
    "Garamond": "EB Garamond",
}


def _web_font(name: Any) -> str:
    """
    A font this browser has for a template's font: the same one, a shipped look-alike, else
    Arimo (bold if it was).
    """
    names = font_names()
    if name in names:
        return name
    text = str(name or "")
    bold = " Bold" if "bold" in text.lower() else ""
    family = WEB_FONT_SUBSTITUTES.get(text[:-5] if text.lower().endswith(" bold") else text, "Arimo")
    for candidate in (family + bold, "Arimo" + bold, "Arimo"):
        if candidate in names:
            return candidate
    return names[0]


def _b64(data: Optional[bytes]) -> Optional[str]:
    import base64
    return base64.b64encode(data).decode("ascii") if data else None


def _unb64(text: Any) -> Optional[bytes]:
    import base64
    import binascii
    if not isinstance(text, str):
        return None
    try:
        return base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError):
        return None


def _picture(saved: Any) -> Optional[Dict[str, Any]]:
    """A picture kept in a template file by the web version: {"name", "data" as base64}."""
    if not isinstance(saved, dict):
        return None
    data = _unb64(saved.get("data"))
    return {"name": str(saved.get("name") or "picture.png"), "data": data} if data else None


def template_from_desktop(data: Any) -> Dict[str, Any]:
    """
    A desktop template (the JSON text or the parsed object) as the page keeps a label:
    {"mode": "text", "label": {...}} or {"mode": "bin", "bin": {"kind", ...}}. Pictures only
    come along from templates the web version saved, since desktop ones point at files on a PC.
    Raises ValueError with a readable message for anything that is not a template.
    """
    import json
    from ui.templates import config_from_dict
    if isinstance(data, (str, bytes, bytearray)) or hasattr(data, "to_bytes"):
        text = _to_bytes(data).decode("utf-8-sig") if not isinstance(data, str) else data
        try:
            data = json.loads(text)
        except ValueError as e:
            raise ValueError(f"This is not a template file: {e}") from e
    else:
        data = _to_dict(data)
    if not isinstance(data, dict):
        raise ValueError("This is not a template file.")
    try:
        cfg = config_from_dict(data)
    except TypeError as e:
        raise ValueError(f"The template has values Cube Labeler cannot read: {e}") from e
    inv = cfg.inventory_config
    if inv is not None:
        from core.inventory_renderer import ComponentLabelConfig
        fields = dataclasses.asdict(inv)
        kind = "component" if isinstance(inv, ComponentLabelConfig) else "fastener"
        fields.pop("custom_icon_path", None)
        fields.pop("custom_tool_icon_path", None)
        fields["kind"] = kind
        fields["icon"] = _picture(data.get("web_bin_icon"))
        icon_field = "icon_type" if kind == "component" else "tool_type"
        if fields[icon_field] == "custom" and fields["icon"] is None:
            fields[icon_field] = "none"
        return {"mode": "bin", "bin": fields}
    label = dataclasses.asdict(cfg)
    for key in ("inventory_config", "image_path", "cut_line", "cut_line_style", "cut_line_position", "auto_cut_hardware"):
        label.pop(key, None)
    label["text"] = label["text"].replace("\\n", "\n")
    label["font_name"] = _web_font(label["font_name"])
    label["image"] = _picture(data.get("web_picture"))
    return {"mode": "text", "label": label}


def template_to_desktop(item: Any) -> str:
    """
    A label from the page ({"mode", "label" or "bin"}, as template_from_desktop gives) as the
    JSON of a desktop template file. Pictures go along as base64 for the web version; the
    desktop app ignores them.
    """
    import json
    from ui.templates import config_to_dict
    item = _to_dict(item)
    if item.get("mode") == "bin":
        bin_data = _to_dict(item.get("bin"))
        icon = bin_data.pop("icon", None)
        icon = _to_dict(icon) if icon else None
        options = {"bin": dict(bin_data, icon_data=icon["data"] if icon else None)}
    else:
        label = _to_dict(item.get("label"))
        image = label.pop("image", None)
        image = _to_dict(image) if image else None
        options = dict(label, image_data=image["data"] if image else None)
        icon = None
    data = config_to_dict(_label_config(options))
    data["image_path"] = None
    inv = data.get("inventory_config")
    if isinstance(inv, dict):
        for key in ("custom_icon_path", "custom_tool_icon_path"):
            if key in inv:
                inv[key] = None
    if item.get("mode") == "bin":
        if icon:
            data["web_bin_icon"] = {"name": icon.get("name"), "data": _b64(_to_bytes(icon["data"]))}
    elif image:
        data["web_picture"] = {"name": image.get("name"), "data": _b64(_to_bytes(image["data"]))}
    return json.dumps(data, indent=2)


def template_presets() -> List[Dict[str, Any]]:
    """The starting points: [{"key", "name", "description", "mode", "label"}]."""
    from ui.templates import BUILTIN_PRESETS, WEB_PRESETS
    out = []
    for key, preset in {**BUILTIN_PRESETS, **WEB_PRESETS}.items():
        item = template_from_desktop(preset["config"])
        out.append({"key": key, "name": preset["name"], "description": preset["description"], **item})
    return out


# --- Backups: the desktop app's .cubebackup files (see core/backup.py for the format) ---

BACKUP_FORMAT = "cube-labeler-backup"
BACKUP_VERSION = 2
OLD_ICON_FORMAT = "cube-labeler-icons"
BACKUP_MAX_ICONS = 5000
BACKUP_MAX_FILES = 2000
BACKUP_MAX_FILE_BYTES = 25 * 1024 * 1024
TOUCH_SUFFIX = ".touch.png"
TEMPLATES_FOLDER = "templates"
FONTS_FOLDER = "fonts"
FONT_SUFFIXES = (".ttf", ".otf", ".ttc")
# The web version's print history, as JSON text the page makes and reads; the desktop app keeps
# it with its other files when it restores settings
HISTORY_FILE = "web_history.json"
# Settings that belong to one device or are secrets never go in a backup (as on the desktop)
_LOCAL_SUFFIXES = ("_api_key", "_api_key_protected")
_LOCAL_KEYS = ("last_serial_port",)
_LOCAL_PREFIXES = ("icon_backup_",)


def _is_local_setting(key: str) -> bool:
    return key in _LOCAL_KEYS or key.startswith(_LOCAL_PREFIXES) or key.endswith(_LOCAL_SUFFIXES)


def _safe_icon_file(name: Any) -> bool:
    return (isinstance(name, str) and name == os.path.basename(name) and "/" not in name and "\\" not in name
            and not name.startswith(".") and name.lower().endswith(".png") and len(name) <= 120)


def _safe_font_file(name: Any) -> bool:
    return (isinstance(name, str) and name == os.path.basename(name) and "/" not in name and "\\" not in name
            and not name.startswith(".") and name.lower().endswith(FONT_SUFFIXES) and len(name) <= 120)


def _is_png(data: bytes) -> bool:
    from PIL import Image
    try:
        with Image.open(io.BytesIO(data)) as img:
            if img.format != "PNG":
                return False
            img.verify()
        return True
    except Exception:
        return False


def template_file_name(name: str) -> str:
    """The file a template called `name` is kept in on the desktop (as ui/templates.py names it)."""
    from ui.templates import template_file_name as desktop_name
    return desktop_name(name)


def _backup_parts(data: Any):
    """The manifest, zip members and data files of a backup made from what the page keeps."""
    data = _to_dict(data)
    icons, members = [], {}
    for item in data.get("icons") or []:
        item = _to_dict(item)
        file = item.get("file")
        if not _safe_icon_file(file):
            continue
        stem = os.path.splitext(file)[0]
        meta = _to_dict(item.get("meta"))
        members[f"icons/{file}"] = _to_bytes(item["icon"])
        original = item.get("original")
        if original is not None and meta.get("edit"):
            members[f"originals/{stem}.png"] = _to_bytes(original)
            touch = touch_png(item.get("touch")) if item.get("touch") is not None else None
            if touch:
                members[f"originals/{stem}{TOUCH_SUFFIX}"] = touch
        else:
            meta.pop("edit", None)
        icons.append({"file": file, "favourite": bool(item.get("favourite")), "meta": meta})
    files = {}
    for template in data.get("templates") or []:
        template = _to_dict(template)
        files[f"{TEMPLATES_FOLDER}/{template_file_name(str(template.get('name') or 'My template'))}"] = (
            str(template["json"]).encode("utf-8"))
    for font in data.get("fonts") or []:
        font = _to_dict(font)
        if _safe_font_file(font.get("filename")):
            files[f"{FONTS_FOLDER}/{font['filename']}"] = _to_bytes(font["data"])
    if isinstance(data.get("history"), str):
        files[HISTORY_FILE] = data["history"].encode("utf-8")
    settings = {k: v for k, v in _to_dict(data.get("settings")).items() if not _is_local_setting(k)}
    manifest = {
        "format": BACKUP_FORMAT,
        "version": BACKUP_VERSION,
        "created": str(data.get("created") or ""),
        "icons": icons,
        "settings": settings,
        "files": sorted(files),
    }
    return manifest, members, files


def make_backup(data: Any) -> bytes:
    """
    A .cubebackup file the desktop app can restore, from what the page keeps:
    {"created", "icons": [{"file", "meta", "favourite", "icon", "original", "touch"}],
     "settings": {...}, "templates": [{"name", "json"}], "fonts": [{"filename", "data"}],
     "history": the print history's JSON text or None}. Icons,
    originals, touch-ups and fonts are bytes; touch-ups may be the page's raw cells. Settings that
    belong to one device are left out.
    """
    import json
    import zipfile
    manifest, members, files = _backup_parts(data)
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False, default=str))
        for name, content in members.items():
            zf.writestr(name, content)
        for name, content in sorted(files.items()):
            zf.writestr(f"data/{name}", content)
    return out.getvalue()


def _same_numbers(value):
    # 100.0 from a desktop file and 100 from the page are the same setting
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, dict):
        return {k: _same_numbers(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_same_numbers(v) for v in value]
    return value


def _item_digests(manifest: Dict[str, Any], members: Dict[str, bytes], files: Dict[str, bytes]) -> Dict[str, Any]:
    """
    A fingerprint of each thing in a backup, for sync to tell what changed on which side:
    {"icons": {file in lower case: hash}, "templates": {file stem in lower case: {"hash", "name"}},
     "settings": {key: the value as JSON}}. Two backups that hold the same icon, template or
    setting give it the same fingerprint, whichever device or app made them.
    """
    import hashlib
    import json

    def sha(*parts: bytes) -> str:
        h = hashlib.sha256()
        for part in parts:
            h.update(hashlib.sha256(part).digest())
        return h.hexdigest()[:32]

    icons = {}
    for item in manifest.get("icons") or []:
        file = item["file"]
        stem = os.path.splitext(file)[0]
        meta = json.dumps(_same_numbers(item.get("meta") or {}), sort_keys=True).encode("utf-8")
        icons[file.lower()] = sha(meta, members.get(f"icons/{file}", b""), members.get(f"originals/{stem}.png", b""),
                                  members.get(f"originals/{stem}{TOUCH_SUFFIX}", b""))
    templates = {}
    for path, content in files.items():
        if not path.startswith(TEMPLATES_FOLDER + "/"):
            continue
        try:
            # Read and written again the way a restore does, so the defaults a template gains on
            # the way in never make it look changed
            content = template_to_desktop(template_from_desktop(content))
            content = json.dumps(_same_numbers(json.loads(content)), sort_keys=True).encode("utf-8")
        except ValueError:
            pass
        stem = os.path.splitext(path.split("/")[-1])[0]
        templates[stem.lower()] = {"hash": sha(content), "name": stem}
    settings = {k: json.dumps(_same_numbers(v), sort_keys=True, default=str)
                for k, v in (manifest.get("settings") or {}).items()}
    return {"icons": icons, "templates": templates, "settings": settings}


def backup_item_digests(data: Any) -> Dict[str, Any]:
    """The fingerprints (see _item_digests) of a backup made from what the page keeps, with each
    template's own name: {"templates": {stem: {"hash", "name"}}} names the template on the page."""
    manifest, members, files = _backup_parts(data)
    digests = _item_digests(manifest, members, files)
    for template in _to_dict(data).get("templates") or []:
        template = _to_dict(template)
        name = str(template.get("name") or "My template")
        stem = os.path.splitext(template_file_name(name))[0].lower()
        if stem in digests["templates"]:
            digests["templates"][stem]["name"] = name
    return digests


def backup_digest(data: Any) -> str:
    """
    Fingerprint of what a backup made from `data` would hold, leaving out when it was made
    and the recently used icons, so automatic backups are skipped when nothing changed.
    """
    import hashlib
    import json
    manifest, members, files = _backup_parts(data)
    manifest.pop("created", None)

    for name, content in list(files.items()):
        if name.startswith(FONTS_FOLDER + "/"):
            continue
        try:
            files[name] = json.dumps(_same_numbers(json.loads(content)), sort_keys=True).encode("utf-8")
        except ValueError:
            pass
    manifest["settings"] = {k: v for k, v in manifest["settings"].items() if k != "icon_recent"}
    h = hashlib.sha256(json.dumps(manifest, sort_keys=True, default=str).encode("utf-8"))
    for name, content in sorted({**members, **{f"data/{k}": v for k, v in files.items()}}.items()):
        h.update(name.encode("utf-8"))
        h.update(hashlib.sha256(content).digest())
    return h.hexdigest()


def open_backup(data: Any) -> Dict[str, Any]:
    """
    Reads a .cubebackup (or an older .cubeicons) file from the desktop app or the web version:
    {"created", "icons": [{"file", "meta", "favourite", "icon", "original", "touch" as cells}],
     "settings": {...} or None, "templates": [{"name", "item"}], "skipped_templates": [names],
     "fonts": [{"filename", "data"}], "history": the web version's print history as JSON text or None,
     "digests": a fingerprint of each icon, template and setting, as backup_item_digests gives them}.
    Raises ValueError with a readable message when it is not a backup this version can read.
    """
    import json
    import zipfile
    try:
        zf = zipfile.ZipFile(io.BytesIO(_to_bytes(data)))
    except (zipfile.BadZipFile, OSError):
        raise ValueError("This is not a Cube Labeler backup.")

    def member(name: str, required: bool = False) -> Optional[bytes]:
        try:
            info = zf.getinfo(name)
        except KeyError:
            if required:
                raise ValueError(f"The backup is missing {name}.")
            return None
        if info.file_size > BACKUP_MAX_FILE_BYTES:
            raise ValueError(f"{name} in the backup is too large.")
        return zf.read(info)

    with zf:
        try:
            manifest = json.loads(member("manifest.json", required=True).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise ValueError("The backup's list of contents is damaged.")
        if not isinstance(manifest, dict) or manifest.get("format") not in (BACKUP_FORMAT, OLD_ICON_FORMAT):
            raise ValueError("This is not a Cube Labeler backup.")
        if not isinstance(manifest.get("version"), int) or manifest["version"] > BACKUP_VERSION:
            raise ValueError("This backup was made by a newer version of Cube Labeler.")
        listed = manifest.get("icons")
        if not isinstance(listed, list) or len(listed) > BACKUP_MAX_ICONS:
            raise ValueError("The backup's list of contents is damaged.")

        icons, seen, raw, raw_files = [], set(), {}, {}
        for item in listed:
            if not isinstance(item, dict) or not _safe_icon_file(item.get("file")) or item["file"].lower() in seen:
                continue
            file = item["file"]
            seen.add(file.lower())
            stem = os.path.splitext(file)[0]
            icon = member(f"icons/{file}", required=True)
            if not _is_png(icon):
                raise ValueError(f"{file} in the backup is not a readable picture.")
            meta = item.get("meta") if isinstance(item.get("meta"), dict) else {}
            original = member(f"originals/{stem}.png")
            if original is not None and not _is_png(original):
                original = None
            touch = member(f"originals/{stem}{TOUCH_SUFFIX}") if original is not None else None
            if original is None:
                meta.pop("edit", None)
            touch = touch if touch and _is_png(touch) else None
            icons.append({
                "file": file, "meta": meta, "favourite": bool(item.get("favourite")), "icon": icon,
                "original": original, "touch": touch_cells(touch) if touch else None,
            })
            raw[f"icons/{file}"] = icon
            if original is not None:
                raw[f"originals/{stem}.png"] = original
            if touch:
                raw[f"originals/{stem}{TOUCH_SUFFIX}"] = touch

        settings, templates, skipped, fonts, history = None, [], [], [], None
        if manifest["format"] == BACKUP_FORMAT:
            settings = manifest.get("settings") if isinstance(manifest.get("settings"), dict) else {}
            listed_files = manifest.get("files") if isinstance(manifest.get("files"), list) else []
            for path in listed_files[:BACKUP_MAX_FILES]:
                if not isinstance(path, str) or ".." in path:
                    continue
                if path == HISTORY_FILE:
                    content = member(f"data/{path}")
                    try:
                        history = content.decode("utf-8") if content is not None else None
                    except UnicodeDecodeError:
                        history = None
                    continue
                if path.startswith(FONTS_FOLDER + "/") and _safe_font_file(path[len(FONTS_FOLDER) + 1:]):
                    content = member(f"data/{path}")
                    if content is not None:
                        fonts.append({"filename": path[len(FONTS_FOLDER) + 1:], "data": content})
                    continue
                if not path.startswith(TEMPLATES_FOLDER + "/"):
                    continue
                name = os.path.splitext(path.split("/")[-1])[0]
                content = member(f"data/{path}")
                if content is None:
                    continue
                try:
                    templates.append({"name": name, "item": template_from_desktop(content)})
                    raw_files[path] = content
                except ValueError:
                    skipped.append(name)
    digests = _item_digests({"icons": [{"file": i["file"], "meta": i["meta"]} for i in icons], "settings": settings},
                            raw, raw_files)
    return {"created": str(manifest.get("created") or ""), "icons": icons, "settings": settings,
            "templates": templates, "skipped_templates": skipped, "fonts": fonts, "history": history,
            "digests": digests}


# --- AI icons: the page sends the request itself, straight from the browser with the key
# kept on the device; Python builds it and reads the answer the desktop app's way ---

def ai_services() -> Dict[str, Any]:
    """The AI services and ready-made instructions: {"services": [...], "presets": [...], "custom"}."""
    from core.ai_generator import CUSTOM, PRESETS, PROVIDERS
    return {
        "services": [{"id": p.id, "name": p.name, "key_url": p.key_url, "key_note": p.key_note,
                      "default_model": p.default_model} for p in PROVIDERS.values()],
        "presets": [{"label": p.label, "mode": p.mode} for p in PRESETS],
        "custom": CUSTOM,
    }


def _ai_service(service: str):
    from core.ai_generator import PROVIDERS
    provider = PROVIDERS.get(service)
    if provider is None:
        raise ValueError(f"Unknown AI service {service!r}.")
    return provider


def ai_models(service: str, model: str = "") -> List[str]:
    """The models to try in order: the chosen one, then the service's fallbacks."""
    provider = _ai_service(service)
    preferred = (model or "").strip() or provider.default_model
    return list(dict.fromkeys(m for m in [preferred] + list(provider.fallback_models) if m))


def ai_request(service: str, picture: Any, preset: str, custom: str, model: str) -> Dict[str, Any]:
    """
    One request to redraw the picture: {"url", "headers", "body", "key_header", "key_prefix"}.
    The page adds the key as key_header: key_prefix + key, so it never passes through Python.
    """
    from core.ai_generator import build_prompt
    provider = _ai_service(service)
    req = provider.request(_open_picture(picture), build_prompt(preset, custom or ""), model)
    [(header, value)] = provider.auth_headers("KEY").items()
    return {"url": req["url"], "headers": req["headers"], "body": req["body"],
            "key_header": header, "key_prefix": value[: -len("KEY")]}


def ai_answer(service: str, model: str, status: int, body: Any) -> Dict[str, Any]:
    """
    Reads the service's answer: {"png"} with the picture, or {"error", "try_next_model"}
    with the service's own message, as the desktop app shows it.
    """
    import json
    from core.ai_generator import ModelNotFoundError
    provider = _ai_service(service)
    text = _to_bytes(body).decode("utf-8", errors="replace") if not isinstance(body, str) else body
    if not 200 <= int(status) < 300:
        try:
            err = json.loads(text).get("error", {})
            msg = err.get("message", text) if isinstance(err, dict) else str(err)
        except Exception:
            msg = text
        error = provider.http_error(int(status), text, f"{provider.name} API error ({status}): {msg}", model)
        return {"error": str(error), "try_next_model": isinstance(error, ModelNotFoundError)}
    try:
        picture = provider.read_answer(json.loads(text), model)
    except RuntimeError as e:
        return {"error": str(e), "try_next_model": False}
    except Exception:
        return {"error": f"{provider.name} sent an answer Cube Labeler cannot read.", "try_next_model": False}
    return {"png": _png(picture.convert("RGBA"))}
