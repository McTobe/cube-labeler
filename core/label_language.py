#!/usr/bin/env python3
"""
Language for the text printed on hardware (bin) labels.
The app's own interface stays English; this only changes what goes on the tape.
"""

from collections import OrderedDict
from dataclasses import dataclass
from typing import Dict, List, Union

from core.config import config_manager
from core.inventory_renderer import ComponentLabelConfig, FastenerLabelConfig

DEFAULT_LANGUAGE = "en"
LANGUAGES = OrderedDict([("en", "English"), ("sv", "Svenska")])

TERMS: Dict[str, Dict[str, str]] = {
    # Fastener categories
    "screws": {"en": "SCREWS", "sv": "SKRUV"},
    "nuts": {"en": "NUTS", "sv": "MUTTER"},
    "washers": {"en": "WASHERS", "sv": "BRICKOR"},
    "threaded_rod": {"en": "THREADED ROD", "sv": "GÄNGSTÅNG"},
    "screws_nuts": {"en": "SCREWS & NUTS", "sv": "SKRUV & MUTTER"},
    "wood_screws": {"en": "WOOD SCREWS", "sv": "TRÄSKRUV"},
    "bolts": {"en": "BOLTS", "sv": "BULTAR"},
    # Component categories
    "bearings": {"en": "BEARINGS", "sv": "KULLAGER"},
    "wago": {"en": "WAGO", "sv": "WAGO"},
    "fuse_holders": {"en": "FUSE HOLDERS", "sv": "SÄKRINGSHÅLLARE"},
    "relays": {"en": "RELAYS", "sv": "RELÄ"},
    "resistors": {"en": "RESISTORS", "sv": "MOTSTÅND"},
    "capacitors": {"en": "CAPACITORS", "sv": "KONDENSATOR"},
    "diodes": {"en": "DIODES", "sv": "DIOD"},
    "connectors": {"en": "CONNECTORS", "sv": "KONTAKTER"},
    # Free text used by presets
    "mixed": {"en": "Mixed", "sv": "Blandade"},
    "sizes": {"en": "sizes", "sv": "storlekar"},
    "kinds": {"en": "kinds", "sv": "sorter"},
    "three_way": {"en": "3-way", "sv": "3-väg"},
    "inline_type": {"en": "Inline type", "sv": "Inline-typ"},
}

FASTENER_CATEGORY_KEYS = ["screws", "nuts", "washers", "threaded_rod", "screws_nuts", "wood_screws", "bolts"]
COMPONENT_CATEGORY_KEYS = [
    "bearings", "wago", "fuse_holders", "relays", "resistors", "capacitors", "diodes", "connectors",
]

InventoryConfig = Union[FastenerLabelConfig, ComponentLabelConfig]


@dataclass
class InventoryPreset:
    preset_id: str
    name: str  # Shown in the app, always English
    config: InventoryConfig


def normalize_language(lang: str) -> str:
    return lang if lang in LANGUAGES else DEFAULT_LANGUAGE


def get_label_language() -> str:
    return normalize_language(str(config_manager.get("label_language", DEFAULT_LANGUAGE)))


def set_label_language(lang: str) -> None:
    config_manager.set("label_language", normalize_language(lang))


def term(key: str, lang: str) -> str:
    return TERMS[key][normalize_language(lang)]


def fastener_categories(lang: str) -> List[str]:
    return [term(k, lang) for k in FASTENER_CATEGORY_KEYS]


def component_categories(lang: str) -> List[str]:
    return [term(k, lang) for k in COMPONENT_CATEGORY_KEYS]


def build_presets(lang: str) -> "OrderedDict[str, InventoryPreset]":
    """Returns the hardware label presets with label text in the given language, keyed by id."""
    t = lambda key: term(key, lang)  # noqa: E731
    presets = [
        InventoryPreset("A1", "A1: Hex head screw (M5 × 20, DIN 933)", FastenerLabelConfig(
            thread_size="M5",
            category=t("screws"),
            compartment_mode="single",
            length_single="x 20",
            standard_line1="DIN 933",
            standard_line2="FZB • 8.8",
            tool_type="external_hex",
            tool_size="8",
        )),
        InventoryPreset("A2", "A2: Socket cap, 2 bins (M3 × 30, × 35)", FastenerLabelConfig(
            thread_size="M3",
            category=t("screws"),
            compartment_mode="dual",
            length_dual_1="x30",
            length_dual_2="x35",
            tool_type="internal_hex",
            tool_size="2.5",
        )),
        InventoryPreset("A3", "A3: Socket cap, 4 bins (M3)", FastenerLabelConfig(
            thread_size="M3",
            category=t("screws"),
            compartment_mode="quad",
            length_quad_1="x25",
            length_quad_2="x18",
            length_quad_3="x20",
            length_quad_4="x16",
            tool_type="internal_hex",
            tool_size="2.5",
        )),
        InventoryPreset("A4", "A4: Hex nut assortment (M5)", FastenerLabelConfig(
            thread_size="M5",
            category=t("nuts"),
            compartment_mode="assortment",
            assortment_line1=t("mixed"),
            assortment_line2=t("kinds"),
            tool_type="external_hex",
            tool_size="8",
        )),
        InventoryPreset("A5", "A5: Washer assortment (M5)", FastenerLabelConfig(
            thread_size="M5",
            category=t("washers"),
            compartment_mode="assortment",
            assortment_line1=t("mixed"),
            assortment_line2=t("sizes"),
            tool_type="washer",
            tool_size="",
        )),
        InventoryPreset("B1", "B1: Ball bearings (608ZZ)", ComponentLabelConfig(
            category_banner=t("bearings"),
            spec_primary="608ZZ",
            spec_secondary="",
            icon_type="ball_bearing",
        )),
        InventoryPreset("B2", "B2: Lever connectors (WAGO 221-413)", ComponentLabelConfig(
            category_banner=t("wago"),
            spec_primary=f"221-413 • {t('three_way')}",
            spec_secondary="0.2 – 4.0 mm²",
            icon_type="wago",
        )),
        InventoryPreset("B3", "B3: Inline fuse holder (16 AWG)", ComponentLabelConfig(
            category_banner=t("fuse_holders"),
            spec_primary="16 AWG / 1.3 mm²",
            spec_secondary=t("inline_type"),
            icon_type="fuse",
        )),
    ]
    return OrderedDict((p.preset_id, p) for p in presets)
