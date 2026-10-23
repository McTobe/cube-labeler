#!/usr/bin/env python3
"""
Byte-level print job builder for the Brother PT-P300BT.

Everything here only builds or reads bytes, with no serial port involved, so the same code
drives the desktop app (pyserial) and the web app (Pyodide + Web Serial).
"""

from typing import Optional, Tuple

from core.ptcbp import (
    serialize_control,
    serialize_control_obj,
    serialize_data,
    CommandSet,
    PrintParameters,
    PrintParameterField,
    PageMode,
    PageModeAdvanced,
    CompressionType,
)
from core.ptstatus import (
    PrinterStatus,
    unpack_status,
    parse_printer_status,
    STATUS_ERROR_OCCURRED,
    STATUS_PRINTING_COMPLETED,
)
from core.specs import DOT_PITCH_MM, PRINTHEAD_DOTS, format_tape_width, tape_width_from_status

STATUS_PACKET_SIZE = 32
LINE_BYTES = PRINTHEAD_DOTS // 8

# Approximate tape speed, used to size the completion timeout
PRINT_SPEED_MM_PER_SEC = 20.0
COMPLETION_TIMEOUT_BASE_SEC = 10.0

PRINT_COMMAND = serialize_control('print')


def init_sequence() -> bytes:
    """Flushes the print buffer and puts the printer into PTCBP raster graphics mode."""
    # 64 null bytes to flush print buffer, ESC @ initialize, ESC i a 1 select PTCBP
    return (
        b"\x00" * 64
        + serialize_control('reset')
        + serialize_control('use_command_set', CommandSet.ptcbp)
    )


def status_request() -> bytes:
    """ESC i S: asks the printer for one 32-byte status packet."""
    return serialize_control('get_status')


def parse_status(raw_bytes: bytes) -> PrinterStatus:
    """Decodes a 32-byte status packet, raising ValueError if it is malformed."""
    return parse_printer_status(unpack_status(raw_bytes))


def tape_dim(status: PrinterStatus) -> Tuple[int, int, int]:
    """The (type, width, length) media triple the job configuration echoes back to the printer."""
    raw = status.raw_status
    return raw.tape_type, raw.tape_width, raw.tape_length


def check_ready(status: PrinterStatus, required_tape_width_mm: Optional[float] = None) -> None:
    """Raises RuntimeError if the printer can't take a job, or has the wrong tape loaded."""
    if not status.is_ready:
        err_msg = ", ".join(status.errors) if status.errors else status.phase_name
        raise RuntimeError(f"Printer is not ready: {err_msg}")
    if required_tape_width_mm is not None:
        loaded = tape_width_from_status(status.tape_width_mm)
        if loaded != float(required_tape_width_mm):
            raise RuntimeError(
                f"This label needs {format_tape_width(required_tape_width_mm)} tape; "
                f"{format_tape_width(loaded)} is loaded."
            )


def job_configuration(
    raster_lines: int,
    tape_dim: Tuple[int, int, int],
    compress: bool = True,
    chaining: bool = False,
    auto_cut: bool = False,
    end_margin: int = 0,
) -> bytes:
    """Builds the configuration packets (dimensions, page modes, margin, compression)."""
    type_, width, length = tape_dim

    # Set media parameters
    active_f = (
        PrintParameterField.width
        | PrintParameterField.quality
        | PrintParameterField.recovery
    )
    params = PrintParameters(
        active_fields=active_f,
        media_type=type_,
        width_mm=width,
        length_mm=length,
        length_px=raster_lines,
        is_follow_up=0,
        sbz=0,
    )
    out = serialize_control_obj('set_print_parameters', params)

    # Advanced page mode (chaining)
    pm2 = 0
    if not chaining:
        pm2 |= PageModeAdvanced.no_page_chaining
    out += serialize_control('set_page_mode_advanced', pm2)

    # Page mode (auto cut)
    pm = 0
    if auto_cut:
        pm |= PageMode.auto_cut
    out += serialize_control('set_page_mode', pm)

    # Margin
    out += serialize_control('set_page_margin', end_margin)

    # Compression mode: TIFF RLE
    ctype = CompressionType.rle if compress else CompressionType.none
    out += serialize_control('compression', ctype)
    return out


def validate_raster(raster_data: bytes) -> int:
    """Returns the number of 128-dot lines, raising ValueError for a malformed raster."""
    if not raster_data or len(raster_data) % LINE_BYTES != 0:
        raise ValueError(
            f"Raster data must be a non-empty multiple of {LINE_BYTES} bytes, got {len(raster_data)}."
        )
    return len(raster_data) // LINE_BYTES


_ZERO_LINE = bytes(LINE_BYTES)


def raster_line(chunk: bytes, compress: bool = True) -> bytes:
    """Encodes one 16-byte raster line, using the short zerofill command for blank lines."""
    if chunk == _ZERO_LINE:
        return serialize_control('zerofill')
    return serialize_data(chunk, 'rle' if compress else 'none')


def raster_lines(raster_data: bytes, compress: bool = True) -> bytes:
    """Encodes a whole raster image as consecutive line commands."""
    return b"".join(
        raster_line(raster_data[i : i + LINE_BYTES], compress)
        for i in range(0, len(raster_data), LINE_BYTES)
    )


def feed_dots(length_mm: float) -> int:
    """Blank raster lines needed to feed length_mm of tape (at least 60)."""
    return max(int(round(length_mm / DOT_PITCH_MM)), 60)


def completion_timeout(raster_lines: int) -> float:
    """Seconds to wait for the printer to confirm a job of this many lines."""
    length_mm = raster_lines * DOT_PITCH_MM
    return COMPLETION_TIMEOUT_BASE_SEC + 2.0 * length_mm / PRINT_SPEED_MM_PER_SEC


def is_completed(status: PrinterStatus) -> bool:
    """True when a status packet confirms the job finished printing."""
    return status.raw_status.status_type == STATUS_PRINTING_COMPLETED


def raise_if_error(status: PrinterStatus) -> None:
    """Raises RuntimeError when a status packet reports a printer error."""
    if status.raw_status.status_type == STATUS_ERROR_OCCURRED:
        err = ", ".join(status.errors) if status.errors else status.phase_name
        raise RuntimeError(f"Printer reported an error: {err}")
