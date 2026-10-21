#!/usr/bin/env python3
"""
Label templates and preset library for Brother PT-P300BT.
"""

import json
from dataclasses import asdict, fields
from typing import Dict, List, Optional
from core.label_renderer import LabelConfig
from core.inventory_renderer import ComponentLabelConfig, FastenerLabelConfig

_INVENTORY_TYPES = {
    "fastener": FastenerLabelConfig,
    "component": ComponentLabelConfig,
}

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


def _known_fields(cls, data: dict) -> dict:
    """Keeps only the keys that are fields of the dataclass, so newer or older files still load."""
    names = {f.name for f in fields(cls)}
    return {k: v for k, v in data.items() if k in names}


def config_to_dict(config: LabelConfig) -> dict:
    data = asdict(config)
    inv = config.inventory_config
    if inv is not None:
        data["inventory_type"] = "fastener" if isinstance(inv, FastenerLabelConfig) else "component"
    return data


def config_from_dict(data: dict) -> LabelConfig:
    """Rebuilds a LabelConfig, including its typed inventory config. Raises ValueError on bad data."""
    if not isinstance(data, dict):
        raise ValueError("Template file does not contain a label configuration object.")
    data = dict(data)
    inv_data = data.pop("inventory_config", None)
    inv_type = data.pop("inventory_type", None)

    cfg = LabelConfig(**_known_fields(LabelConfig, data))

    if inv_data is not None:
        if not isinstance(inv_data, dict):
            raise ValueError("Template has an invalid hardware label section.")
        if inv_type is None:
            # Files saved before the type tag existed: fasteners always have a thread size
            inv_type = "fastener" if "thread_size" in inv_data else "component"
        inv_cls = _INVENTORY_TYPES.get(inv_type)
        if inv_cls is None:
            raise ValueError(f"Unknown hardware label type '{inv_type}'.")
        inv_fields = _known_fields(inv_cls, inv_data)
        if inv_cls is FastenerLabelConfig and "simple_drive_icon" not in inv_data:
            # Saved before drive icons came from the icon library: keep the drawn icon it was made with
            inv_fields["simple_drive_icon"] = True
        cfg.inventory_config = inv_cls(**inv_fields)
    return cfg


def export_config_to_json(config: LabelConfig, file_path: str) -> bool:
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(config_to_dict(config), f, indent=2)
        return True
    except Exception:
        return False


def load_config_from_json(file_path: str) -> LabelConfig:
    """Loads a template file. Raises OSError or ValueError with a readable message on failure."""
    with open(file_path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Template is not valid JSON: {e}") from e
    try:
        return config_from_dict(data)
    except TypeError as e:
        raise ValueError(f"Template has invalid values: {e}") from e


def import_config_from_json(file_path: str) -> Optional[LabelConfig]:
    try:
        return load_config_from_json(file_path)
    except Exception:
        return None
