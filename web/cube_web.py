"""
Python side of the Cube Labeler web app, loaded by Pyodide.

The page calls these functions to render labels and to build or read printer bytes;
JavaScript only moves those bytes over Web Serial. Everything here also runs on CPython,
which is how tests/test_web_bridge.py checks it.
"""

import dataclasses
import io
import os
import tempfile
from typing import Any, Dict, Optional

from core import protocol
from core.specs import TAPE_SPECS

USER_FONT_DIR = os.path.join(tempfile.gettempdir(), "cube-labeler-fonts")

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


def render_label(options: Any) -> Dict[str, Any]:
    """
    Renders one text label. Options use LabelConfig field names (text, font_name,
    tape_width_mm, auto_fit_font, fixed_font_size, alignment, qr_enabled, qr_data, ...);
    unknown keys are ignored. Returns the preview PNG, the print raster and the metrics.
    """
    from core.label_renderer import LabelConfig
    fields = {f.name for f in dataclasses.fields(LabelConfig)}
    opts = {k: v for k, v in _to_dict(options).items() if k in fields}
    preview, _, raster, metrics = _get_renderer().render(LabelConfig(**opts))

    png = io.BytesIO()
    preview.save(png, format="PNG")
    return {
        "preview_png": png.getvalue(),
        "raster": raster,
        "metrics": dataclasses.asdict(metrics),
    }


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
        auto_cut=bool(opts.get("auto_cut", True)),
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
