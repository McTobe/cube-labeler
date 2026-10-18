#!/usr/bin/env python3
"""
Shared physical constants for the Brother PT-P300BT printhead and supported tapes.
"""

# Millimetres per raster line. The PT-P300BT is specified at 180 dpi (25.4 / 180 = 0.141 mm),
# but labels have historically been laid out at 0.149 mm. Measure a fixed-width label on real
# hardware before changing this; every length calculation in the app derives from it.
DOT_PITCH_MM = 0.149

PRINTHEAD_DOTS = 128  # Total printhead width in dots

# Height specifications per tape width (mm). Keys are floats so 3.5 mm tape is addressable.
TAPE_SPECS = {
    12.0: {"printable_height": 64, "tape_height": 86, "canvas_height": 88},
    9.0: {"printable_height": 48, "tape_height": 66, "canvas_height": 70},
    6.0: {"printable_height": 32, "tape_height": 46, "canvas_height": 50},
    3.5: {"printable_height": 24, "tape_height": 32, "canvas_height": 36},
}

# Hardware inventory layouts are designed for 64 printable dots and only support 12 mm tape.
INVENTORY_TAPE_WIDTH_MM = 12.0


def get_tape_spec(tape_width_mm: float) -> dict:
    """Returns the spec for a supported tape width, raising ValueError for unknown widths."""
    try:
        key = float(tape_width_mm)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid tape width: {tape_width_mm!r}")
    if key not in TAPE_SPECS:
        supported = ", ".join(format_tape_width(w) for w in TAPE_SPECS)
        raise ValueError(f"Unsupported tape width {format_tape_width(key)} (supported: {supported})")
    return TAPE_SPECS[key]


def format_tape_width(tape_width_mm: float) -> str:
    """Formats a tape width the way the UI shows it, e.g. 12.0 -> '12mm', 3.5 -> '3.5mm'."""
    value = float(tape_width_mm)
    return f"{value:g}mm"


def tape_width_from_status(reported_mm: int) -> float:
    """Maps the printer's integer tape-width byte to a supported tape width.

    The status register reports whole millimetres, so 3.5 mm tape is reported as 3 or 4.
    """
    if reported_mm in (3, 4):
        return 3.5
    return float(reported_mm)
