#!/usr/bin/env python3
"""
Icon Library Manager for Cube Labeler.
Indexes built-in and user-generated monochrome icons, providing categorization,
search, and persistence across app sessions.
"""

import os
import sys
from dataclasses import dataclass
from typing import List, Dict, Optional
from PIL import Image

from core.config import config_manager


@dataclass
class IconItem:
    id: str
    title: str
    category: str
    file_path: str
    keywords: List[str]

    @property
    def is_user_custom(self) -> bool:
        return self.category in ("My Icons", "user")


# Metadata dictionaries for human-readable titles and search keywords
METADATA_REGISTRY: Dict[str, Dict[str, any]] = {
    # Fasteners
    "hex_socket": {"title": "Hex Socket (Allen / DIN 912)", "keywords": ["allen", "hex", "socket", "inbus", "drive", "bolt"]},
    "torx": {"title": "Torx Star Drive", "keywords": ["torx", "star", "t10", "t15", "t20", "t25", "t30", "tx"]},
    "phillips": {"title": "Phillips Cross (PH)", "keywords": ["phillips", "cross", "ph", "screw"]},
    "slotted": {"title": "Slotted Flat (SL)", "keywords": ["slotted", "flat", "slot", "minus", "screw"]},
    "pozidriv": {"title": "Pozidriv Cross (PZ)", "keywords": ["pozidriv", "pz", "cross", "star"]},
    "robertson": {"title": "Robertson Square", "keywords": ["robertson", "square", "cube"]},
    "hex_bolt": {"title": "Hex Head Bolt (DIN 933)", "keywords": ["bolt", "hex", "screw", "wrench", "external"]},
    "hex_nut": {"title": "Hex Nut (DIN 934)", "keywords": ["nut", "hex", "thread", "mutter"]},
    "flat_washer": {"title": "Flat Washer (DIN 125)", "keywords": ["washer", "bricka", "flat", "ring", "donut"]},
    "spring_washer": {"title": "Spring Lock Washer (DIN 127)", "keywords": ["washer", "spring", "lock", "split"]},
    "countersunk": {"title": "Countersunk Screw (DIN 7991)", "keywords": ["countersunk", "flathead", "conical", "screw"]},
    "standoff": {"title": "Hex PCB Standoff", "keywords": ["standoff", "spacer", "pcb", "hex", "threaded"]},

    # Engineering
    "bearing_608zz": {"title": "Ball Bearing (608ZZ)", "keywords": ["bearing", "kullager", "ball", "608", "roller", "engineering"]},
    "gear": {"title": "Spur Gear / Cogwheel", "keywords": ["gear", "kugghjul", "cog", "sprocket", "pinion", "engineering"]},
    "spring": {"title": "Compression Spring", "keywords": ["spring", "fjäder", "coil", "compression", "engineering"]},

    # Electronics
    "fuse_inline": {"title": "Cartridge Glass Fuse", "keywords": ["fuse", "säkring", "glass", "inline", "cartridge"]},
    "resistor": {"title": "Resistor (IEEE Symbol)", "keywords": ["resistor", "motstånd", "ohm", "schematic"]},
    "capacitor_ceramic": {"title": "Ceramic Capacitor", "keywords": ["capacitor", "kondensator", "ceramic", "pf", "nf"]},
    "capacitor_elec": {"title": "Electrolytic Capacitor", "keywords": ["capacitor", "electrolytic", "kondensator", "polarized", "uf"]},
    "diode": {"title": "Diode (Semiconductor)", "keywords": ["diode", "rectifier", "1n4007", "semiconductor"]},
    "led": {"title": "Light Emitting Diode (LED)", "keywords": ["led", "light", "diode", "lamp", "emitter"]},
    "ic_dip": {"title": "IC Chip (DIP Package)", "keywords": ["ic", "chip", "dip", "microcontroller", "integrated circuit"]},
    "ground": {"title": "Chassis / Earth Ground", "keywords": ["ground", "earth", "gnd", "chassis"]},
    "usb_c": {"title": "USB-C Port / Connector", "keywords": ["usb", "usb-c", "type-c", "port", "cable"]},

    # Tools
    "caliper": {"title": "Digital Caliper", "keywords": ["caliper", "skjutmått", "vernier", "measure", "tool"]},
    "wrench": {"title": "Open-End Wrench", "keywords": ["wrench", "spanner", "fastyckel", "tool"]},
    "soldering_iron": {"title": "Soldering Iron", "keywords": ["soldering", "iron", "lödkolv", "heat", "solder"]},
    "drill_bit": {"title": "Spiral Drill Bit", "keywords": ["drill", "bit", "borr", "flute", "spiral"]},

    # Symbols
    "high_voltage": {"title": "High Voltage Warning", "keywords": ["high voltage", "danger", "electric", "shock", "lightning"]},
    "caution": {"title": "Caution / Attention", "keywords": ["caution", "warning", "attention", "triangle"]},
    "esd_warning": {"title": "ESD Sensitive Device", "keywords": ["esd", "static", "sensitive", "hand", "electronic"]},
    "recycle": {"title": "Recycle / Sustainable", "keywords": ["recycle", "loop", "arrows", "waste", "eco"]},
}


class IconManager:
    """Manages icon discovery, categorization, search, and user additions."""

    CATEGORIES = ["All", "Fasteners", "Engineering", "Electronics", "Tools", "Symbols", "My Icons"]

    def __init__(self):
        self._icons: List[IconItem] = []
        self._cache: Dict[str, Image.Image] = {}
        self.reload()

    def _get_base_icons_dir(self) -> str:
        if getattr(sys, "frozen", False):
            base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
            icons_path = os.path.join(base, "assets", "icons")
            if os.path.isdir(icons_path):
                return icons_path

        # Standard source directory
        proj_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(proj_root, "assets", "icons")

    def reload(self):
        """Scans both bundled and user icon directories."""
        self._icons = []
        base_dir = self._get_base_icons_dir()

        folder_cat_map = {
            "fasteners": "Fasteners",
            "engineering": "Engineering",
            "electronics": "Electronics",
            "tools": "Tools",
            "symbols": "Symbols",
            "user": "My Icons",
        }

        # 1. Bundled icons
        if os.path.isdir(base_dir):
            for folder, cat_name in folder_cat_map.items():
                cat_dir = os.path.join(base_dir, folder)
                if os.path.isdir(cat_dir):
                    self._scan_folder(cat_dir, cat_name)

        # 2. Persistent User Icons directory in ~/.printlabel/icons
        user_dir = config_manager.user_icons_dir
        if os.path.isdir(user_dir):
            self._scan_folder(user_dir, "My Icons")

    def _scan_folder(self, folder_path: str, category_name: str):
        for entry in os.scandir(folder_path):
            if entry.is_file() and entry.name.lower().endswith((".png", ".jpg", ".jpeg", ".bmp")):
                icon_id = os.path.splitext(entry.name)[0]
                meta = METADATA_REGISTRY.get(icon_id.lower(), {})
                
                title = meta.get("title", icon_id.replace("_", " ").title())
                keywords = meta.get("keywords", [icon_id.lower(), category_name.lower()])
                
                # Check for duplicate IDs
                if not any(item.file_path == entry.path for item in self._icons):
                    self._icons.append(IconItem(
                        id=icon_id,
                        title=title,
                        category=category_name,
                        file_path=entry.path,
                        keywords=keywords
                    ))

    def list_icons(self, category: str = "All", search_query: str = "") -> List[IconItem]:
        """Filters icons by category and search keyword."""
        q = search_query.strip().lower()
        results = []

        for icon in self._icons:
            # Category match
            if category != "All" and icon.category != category:
                continue

            # Search match
            if q:
                matches = (
                    q in icon.id.lower()
                    or q in icon.title.lower()
                    or any(q in kw for kw in icon.keywords)
                )
                if not matches:
                    continue

            results.append(icon)

        # Sort: bundled catalog first by title, then user icons
        results.sort(key=lambda x: (x.category == "My Icons", x.title.lower()))
        return results

    def get_icon_by_id(self, icon_id: str) -> Optional[IconItem]:
        for item in self._icons:
            if item.id.lower() == icon_id.lower():
                return item
        return None

    def save_user_icon(self, image: Image.Image, name: str) -> IconItem:
        """Saves a user/AI generated image into the persistent user icons folder."""
        safe_name = "".join(c for c in name if c.isalnum() or c in ("_", "-")).strip("_")
        if not safe_name:
            safe_name = "custom_icon"

        user_dir = config_manager.user_icons_dir
        os.makedirs(user_dir, exist_ok=True)
        target_path = os.path.join(user_dir, f"{safe_name}.png")

        # Handle collisions
        counter = 1
        while os.path.isfile(target_path):
            target_path = os.path.join(user_dir, f"{safe_name}_{counter}.png")
            counter += 1

        image.save(target_path, "PNG")
        self.reload()

        for item in self._icons:
            if item.file_path == target_path:
                return item

        # Fallback return
        return IconItem(
            id=os.path.splitext(os.path.basename(target_path))[0],
            title=safe_name.replace("_", " ").title(),
            category="My Icons",
            file_path=target_path,
            keywords=[safe_name.lower(), "custom", "user"]
        )


# Global singleton
icon_manager = IconManager()
