#!/usr/bin/env python3
"""
Icon Library Manager for Cube Labeler.
Indexes built-in and user-generated monochrome icons, providing categorization,
search, and persistence across app sessions.
"""

import json
import os
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from PIL import Image

from core.config import config_manager

# Built-in icons live in one folder per category under assets/icons; catalog.json there
# lists the categories in display order and gives each icon its title and search words
CATALOG_FILE = "catalog.json"
USER_CATEGORY = "My Icons"


@dataclass
class IconItem:
    id: str
    title: str
    category: str
    file_path: str
    keywords: List[str]

    @property
    def is_user_custom(self) -> bool:
        return self.category == USER_CATEGORY


def load_catalog(icons_dir: str) -> Dict[str, Any]:
    """Reads the built-in icon catalog: category folders in display order plus titles and search words."""
    try:
        with open(os.path.join(icons_dir, CATALOG_FILE), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {"categories": [], "icons": {}}
    return {"categories": data.get("categories", []), "icons": data.get("icons", {})}


class IconManager:
    """Manages icon discovery, categorization, search, and user additions."""

    def __init__(self):
        self._icons: List[IconItem] = []
        self._metadata: Dict[str, Dict[str, Any]] = {}
        self.CATEGORIES: List[str] = ["All", USER_CATEGORY]
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

        catalog = load_catalog(base_dir)
        self._metadata = catalog["icons"]
        categories = [(c["folder"], c["name"]) for c in catalog["categories"]]
        self.CATEGORIES = ["All"] + [name for _, name in categories] + [USER_CATEGORY]

        # 1. Bundled icons, one folder per category
        for folder, cat_name in categories:
            cat_dir = os.path.join(base_dir, folder)
            if os.path.isdir(cat_dir):
                self._scan_folder(cat_dir, cat_name)

        # 2. Persistent User Icons directory in ~/.printlabel/icons
        user_dir = config_manager.user_icons_dir
        if os.path.isdir(user_dir):
            self._scan_folder(user_dir, USER_CATEGORY)

    def _scan_folder(self, folder_path: str, category_name: str):
        for entry in os.scandir(folder_path):
            if entry.is_file() and entry.name.lower().endswith((".png", ".jpg", ".jpeg", ".bmp")):
                icon_id = os.path.splitext(entry.name)[0]
                meta = self._metadata.get(icon_id.lower(), {})
                
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
        results.sort(key=lambda x: (x.category == USER_CATEGORY, x.title.lower()))
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
            category=USER_CATEGORY,
            file_path=target_path,
            keywords=[safe_name.lower(), "custom", "user"]
        )


# Global singleton
icon_manager = IconManager()
