#!/usr/bin/env python3
"""
PT-P300BT status register decoder and helper tables.
Based on the status decoding in Ircama/PT-P300BT (see LICENSE).
Decodes the 32-byte status packet returned by Brother label printers.
"""

import ctypes
from dataclasses import dataclass
from typing import List, Optional

POWER = {
    0: 'Battery full',
    1: 'Battery half',
    2: 'Battery low',
    3: 'Battery critical',
    4: 'AC Adapter',
}

MODELS = {
    0x38: 'QL-800',
    0x39: 'QL-810W',
    0x41: 'QL-820NWB',
    0x66: 'PT-E550W',
    0x68: 'PT-P750W',
    0x6f: 'PT-P900W',
    0x70: 'PT-P950NW',
    0x72: 'PT-P300BT',
}

ERR_FLAGS = {
    0: 'Replace media',
    1: 'Expansion buffer full',
    2: 'Communication error',
    3: 'Communication buffer full',
    4: 'Cover opened',
    5: 'Overheat/Cancelled on printer side',
    6: 'Feed error',
    7: 'General system error',
    8: 'Media not loaded',
    9: 'End of media (Page too long)',
    10: 'Cutter jammed',
    11: 'Low battery',
    12: 'Printer in use',
    13: 'Printer not powered',
    14: 'Overvoltage',
    15: 'Fan error',
}

TAPE_TYPE = {
    0x00: 'Not loaded',
    0x01: 'Laminated (TZexxx)',
    0x03: 'Non-laminated (TZeNxxx)',
    0x11: 'Heat shrink tube (HSexxx)',
    0x4a: 'Continuous tape',
    0x4b: 'Die-cut labels',
    0xff: 'Unsupported',
}

PHASES = {
    0x000000: 'Ready',
    0x000001: 'Feed',
    0x010000: 'Printing',
    0x010014: 'Cover open while receiving',
}

TAPE_BGCOLORS = {
    0x00: ('None', '#FFFFFF'),
    0x01: ('White', '#FFFFFF'),
    0x02: ('Other', '#E0E0E0'),
    0x03: ('Clear', '#E8F4F8'),
    0x04: ('Red', '#E53935'),
    0x05: ('Blue', '#1E88E5'),
    0x06: ('Yellow', '#FDD835'),
    0x07: ('Green', '#43A047'),
    0x08: ('Black', '#212121'),
    0x09: ('Clear (White text)', '#E8F4F8'),
    0x20: ('Matte white', '#F5F5F5'),
    0x21: ('Matte clear', '#ECEFF1'),
    0x22: ('Matte silver', '#B0BEC5'),
    0x23: ('Satin gold', '#D4AF37'),
    0x24: ('Satin silver', '#CFD8DC'),
    0x30: ('Blue (D)', '#1565C0'),
    0x31: ('Red (D)', '#C62828'),
    0x40: ('Fluorescent orange', '#FF6D00'),
    0x41: ('Fluorescent yellow', '#EEFF41'),
    0x50: ('Berry pink (S)', '#D81B60'),
    0x51: ('Light gray (S)', '#BDBDBD'),
    0x52: ('Lime green (S)', '#7CB342'),
    0x60: ('Yellow (F)', '#FFFF00'),
    0x61: ('Pink (F)', '#FF4081'),
    0x62: ('Blue (F)', '#00B0FF'),
    0x70: ('White (Heat shrink)', '#FFFFFF'),
    0x90: ('White (Flex ID)', '#FFFFFF'),
    0x91: ('Yellow (Flex ID)', '#FFF176'),
    0xf0: ('Head cleaner', '#EEEEEE'),
    0xf1: ('Stencil', '#B0BEC5'),
    0xff: ('Unsupported', '#FFFFFF'),
}

TAPE_FGCOLORS = {
    0x00: ('None', '#000000'),
    0x01: ('White', '#FFFFFF'),
    0x02: ('Other', '#333333'),
    0x04: ('Red', '#D32F2F'),
    0x05: ('Blue', '#1976D2'),
    0x08: ('Black', '#000000'),
    0x0a: ('Gold', '#FFD700'),
    0x62: ('Blue (F)', '#0288D1'),
    0xf0: ('Head cleaner', '#000000'),
    0xf1: ('Stencil', '#000000'),
    0xff: ('Unsupported', '#000000'),
}

PRINT_FLAGS = {
    6: 'Auto cut',
    7: 'Hardware mirroring',
}

STATUS_TYPE = {
    0x00: "Reply to status request",
    0x01: "Printing completed",
    0x02: "Error occurred",
    0x03: "IF mode finished",
    0x04: "Power off",
    0x05: "Notification",
    0x06: "Phase change",
}

STATUS_PRINTING_COMPLETED = 0x01
STATUS_ERROR_OCCURRED = 0x02

NOTIFICATIONS = {
    0x00: 'N/A',
    0x01: 'Cover open',
    0x02: 'Cover close',
}


class StatusRegister(ctypes.BigEndianStructure):
    _pack_ = 1
    _fields_ = (
        ('magic', ctypes.c_char * 4),
        ('model', ctypes.c_uint8),
        ('country', ctypes.c_uint8),
        ('_err2', ctypes.c_uint8),
        ('_power', ctypes.c_uint8),
        ('err', ctypes.c_uint16),
        ('tape_width', ctypes.c_uint8),
        ('tape_type', ctypes.c_uint8),
        ('colors', ctypes.c_uint8),
        ('fonts', ctypes.c_uint8),
        ('_sbz0', ctypes.c_uint8),
        ('mode', ctypes.c_uint8),
        ('density', ctypes.c_uint8),
        ('tape_length', ctypes.c_uint8),
        ('status_type', ctypes.c_uint8),
        ('phase_type', ctypes.c_uint8),
        ('phase', ctypes.c_uint16),
        ('notification', ctypes.c_uint8),
        ('expansion_area', ctypes.c_uint8),
        ('tape_bgcolor', ctypes.c_uint8),
        ('tape_fgcolor', ctypes.c_uint8),
        ('hw_settings', ctypes.c_uint32),
        ('_sbz1', ctypes.c_uint8 * 2),
    )


@dataclass
class PrinterStatus:
    raw_status: StatusRegister
    model_name: str
    power_status: str
    errors: List[str]
    tape_width_mm: int
    tape_type_name: str
    bg_color_name: str
    bg_color_hex: str
    fg_color_name: str
    fg_color_hex: str
    phase_name: str
    status_type_name: str
    notification_name: str
    is_ready: bool
    tape_loaded: bool
    # False when a print was sent but the printer never confirmed completion before the timeout
    completion_confirmed: bool = True


def describe_code(code: int, table: dict) -> str:
    val = table.get(code, "Unknown")
    if isinstance(val, tuple):
        val = val[0]
    return f'{val} (0x{code:02x})'


def describe_flags(flagset: int, descset: dict) -> List[str]:
    flags = []
    ctr = 0
    while flagset != 0:
        if flagset & 1:
            flags.append(descset.get(ctr, f'bit{ctr}'))
        ctr += 1
        flagset >>= 1
    return flags


def unpack_status(bytes_: bytes) -> StatusRegister:
    if len(bytes_) != 32:
        raise ValueError(f'Status must be exactly 32 bytes long, received {len(bytes_)} bytes.')
    # Brother status packets start with print head mark 0x80 and packet size 0x20
    if bytes_[0] != 0x80 or bytes_[1] != 0x20:
        raise ValueError(
            'Response is not a Brother printer status packet. '
            'Check that the selected COM port is the printer.'
        )
    status = StatusRegister()
    ctypes.memmove(ctypes.addressof(status), bytes_, ctypes.sizeof(status))
    return status


def parse_printer_status(raw: StatusRegister) -> PrinterStatus:
    model_name = MODELS.get(raw.model, f'Unknown (0x{raw.model:02x})')
    power_desc = POWER.get(raw._power, f'Unknown ({raw._power})')
    errors = describe_flags(raw.err, ERR_FLAGS)
    tape_width = raw.tape_width
    tape_type_name = TAPE_TYPE.get(raw.tape_type, f'Unknown (0x{raw.tape_type:02x})')
    
    bg_info = TAPE_BGCOLORS.get(raw.tape_bgcolor, ('White', '#FFFFFF'))
    fg_info = TAPE_FGCOLORS.get(raw.tape_fgcolor, ('Black', '#000000'))
    
    phase_code = (raw.phase_type << 16) | raw.phase
    phase_desc = PHASES.get(phase_code, f'Phase 0x{phase_code:06x}')
    status_desc = STATUS_TYPE.get(raw.status_type, f'0x{raw.status_type:02x}')
    notif_desc = NOTIFICATIONS.get(raw.notification, 'N/A')
    
    tape_loaded = raw.tape_type != 0x00 and raw.tape_width > 0
    is_ready = (raw.err == 0 and raw.phase_type == 0 and raw.phase == 0 and tape_loaded)

    return PrinterStatus(
        raw_status=raw,
        model_name=model_name,
        power_status=power_desc,
        errors=errors,
        tape_width_mm=tape_width,
        tape_type_name=tape_type_name,
        bg_color_name=bg_info[0],
        bg_color_hex=bg_info[1],
        fg_color_name=fg_info[0],
        fg_color_hex=fg_info[1],
        phase_name=phase_desc,
        status_type_name=status_desc,
        notification_name=notif_desc,
        is_ready=is_ready,
        tape_loaded=tape_loaded,
    )
