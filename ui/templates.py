#!/usr/bin/env python3
"""
Label templates and preset library for Brother PT-P300BT.
"""

import json
from dataclasses import asdict
from typing import Dict, List, Optional
from core.label_renderer import LabelConfig

BUILTIN_PRESETS: Dict[str, dict] = {
    "Storage Box": {
        "name": "Storage Box / Shelf",
        "description": "Bold two-line label for bins, toolboxes, and shelves.",
        "config": {
            "text": "ELECTRONICS & CORDS\\nShelf 2 - Row B",
            "font_name": "Arial Bold",
            "auto_fit_font": True,
            "alignment": "center",
            "line_spacing": 1.25,
            "h_padding": 12,
            "qr_enabled": False,
            "tape_width_mm": 12,
            "tape_bg_color": "#FFFFFF",
            "tape_fg_color": "#000000",
        }
    },
    "Cable Flag / Wrap": {
        "name": "Cable Wrap / Wire Flag",
        "description": "Double-printed text with margin for folding around cables.",
        "config": {
            "text": "ROUTER - ETH 1           ROUTER - ETH 1",
            "font_name": "Consolas Bold",
            "auto_fit_font": True,
            "alignment": "center",
            "line_spacing": 1.0,
            "h_padding": 16,
            "qr_enabled": False,
            "tape_width_mm": 12,
            "tape_bg_color": "#FDD835",
            "tape_fg_color": "#000000",
        }
    },
    "WiFi Guest Access": {
        "name": "WiFi Guest QR Login",
        "description": "Scan-to-connect WiFi QR code on the left with credentials on right.",
        "config": {
            "text": "GUEST WI-FI\\nScan to Connect\\nPass: Welcome2026",
            "font_name": "Segoe UI Bold",
            "auto_fit_font": True,
            "alignment": "left",
            "line_spacing": 1.15,
            "h_padding": 10,
            "qr_enabled": True,
            "qr_data": "WIFI:S:MyGuestNetwork;T:WPA;P:Welcome2026;;",
            "qr_position": "left",
            "qr_scale": 0.95,
            "tape_width_mm": 12,
            "tape_bg_color": "#FFFFFF",
            "tape_fg_color": "#000000",
        }
    },
    "Spice / Pantry Jar": {
        "name": "Kitchen Spice Jar",
        "description": "Clean, elegant food container label.",
        "config": {
            "text": "SWEET PAPRIKA\\nOrganic - Harvest 2026",
            "font_name": "Calibri",
            "auto_fit_font": True,
            "alignment": "center",
            "line_spacing": 1.2,
            "h_padding": 10,
            "qr_enabled": False,
            "tape_width_mm": 12,
            "tape_bg_color": "#ECEFF1",
            "tape_fg_color": "#000000",
        }
    },
    "Asset / Serial Tag": {
        "name": "Equipment Asset Tag",
        "description": "Inventory management tag with asset ID and QR link.",
        "config": {
            "text": "COMPANY ASSET\\nID: LAB-SYS-0924\\nDo Not Remove",
            "font_name": "Consolas",
            "auto_fit_font": True,
            "alignment": "left",
            "line_spacing": 1.1,
            "h_padding": 8,
            "qr_enabled": True,
            "qr_data": "https://inventory.local/asset/LAB-SYS-0924",
            "qr_position": "left",
            "qr_scale": 0.9,
            "tape_width_mm": 12,
            "tape_bg_color": "#FFFFFF",
            "tape_fg_color": "#000000",
        }
    },
    "Name Badge / Shipping": {
        "name": "Name Badge / Shipping",
        "description": "Clean personal name badge or shipping label.",
        "config": {
            "text": "Tobias Miller\\nSoftware Engineer\\nAntigravity Project",
            "font_name": "Segoe UI",
            "auto_fit_font": True,
            "alignment": "center",
            "line_spacing": 1.15,
            "h_padding": 12,
            "qr_enabled": False,
            "tape_width_mm": 12,
            "tape_bg_color": "#FFFFFF",
            "tape_fg_color": "#000000",
        }
    }
}


def get_preset_names() -> List[str]:
    return list(BUILTIN_PRESETS.keys())


def load_preset(name: str) -> Optional[dict]:
    if name in BUILTIN_PRESETS:
        return BUILTIN_PRESETS[name]["config"]
    return None


def export_config_to_json(config: LabelConfig, file_path: str) -> bool:
    try:
        data = asdict(config)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return True
    except Exception:
        return False


def import_config_from_json(file_path: str) -> Optional[LabelConfig]:
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return LabelConfig(**data)
    except Exception:
        return None
