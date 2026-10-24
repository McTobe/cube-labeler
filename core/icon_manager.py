#!/usr/bin/env python3
"""
Icon Library Manager for Cube Labeler.
Indexes built-in and user-generated monochrome icons, providing categorization,
search, favourites, recently used icons and management of the user's own icons.
"""

import json
import os
import sys
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple
from PIL import Image

from core.config import config_manager
from core.icon_editor import IconEdit, print_dots, prepare_original

# Built-in icons live in one folder per category under assets/icons; catalog.json there
# lists the categories in display order and gives each icon its title and search words
CATALOG_FILE = "catalog.json"
USER_CATEGORY = "My Icons"
# The user's own icons keep their titles, categories and search words next to them
USER_META_FILE = "icons.json"
# Originals and touch-ups of the user's icons, so an icon can be edited again later
ORIGINALS_DIR = "originals"
TOUCH_SUFFIX = ".touch.png"

# Views of the library that are not categories of their own
ALL = "All"
FAVOURITES = "Favourites"
RECENT = "Recently used"
RECENT_LIMIT = 12

ICON_EXTENSIONS = (".png", ".jpg", ".jpeg", ".bmp")

# How an icon prints on a 12 mm bin label: shrunk to this many dots, then cut to black and white
PRINT_PREVIEW_DOTS = 56
PRINT_THRESHOLD = 100


@dataclass
class IconItem:
    id: str
    title: str
    category: str
    file_path: str
    keywords: List[str]
    user: bool = False

    @property
    def is_user_custom(self) -> bool:
        return self.user

    @property
    def key(self) -> str:
        """Stable name for favourites and recent icons: category folder (or "user") and file name."""
        folder = "user" if self.user else os.path.basename(os.path.dirname(self.file_path))
        return f"{folder}/{os.path.basename(self.file_path)}"


def load_catalog(icons_dir: str) -> Dict[str, Any]:
    """Reads the built-in icon catalog: category folders in display order plus titles and search words."""
    try:
        with open(os.path.join(icons_dir, CATALOG_FILE), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {"categories": [], "icons": {}}
    return {"categories": data.get("categories", []), "icons": data.get("icons", {})}


def print_preview(image_path: str, dots: int = PRINT_PREVIEW_DOTS) -> Optional[Image.Image]:
    """The icon as it comes out on tape: cropped to its ink, shrunk to `dots` and cut to black and white."""
    try:
        with Image.open(image_path) as src:
            img = src.convert("RGBA")
    except Exception:
        return None
    return print_dots(img, dots, PRINT_THRESHOLD)


def parse_keywords(text: str) -> List[str]:
    """Search words typed as a comma separated list."""
    return [w.strip().lower() for w in text.split(",") if w.strip()]


class IconManager:
    """Manages icon discovery, categorization, search, and user additions."""

    def __init__(self, user_dir: Optional[str] = None):
        self._icons: List[IconItem] = []
        self._metadata: Dict[str, Dict[str, Any]] = {}
        self._user_meta: Dict[str, Dict[str, Any]] = {}
        self._user_dir = user_dir
        self.CATEGORIES: List[str] = [ALL, USER_CATEGORY]
        self._cache: Dict[str, Image.Image] = {}
        # Called after the user's icons change, e.g. to write an automatic backup
        self.change_listeners: List[Callable[[], None]] = []
        self.reload()

    @property
    def user_dir(self) -> str:
        return self._user_dir or config_manager.user_icons_dir

    @property
    def views(self) -> List[str]:
        """Everything the library window lists in its sidebar, in order."""
        return [ALL, FAVOURITES, RECENT] + self.CATEGORIES[1:]

    @property
    def built_in_categories(self) -> List[str]:
        """Categories a user icon can be filed under."""
        return self.CATEGORIES[1:-1]

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
        self.CATEGORIES = [ALL] + [name for _, name in categories] + [USER_CATEGORY]

        # 1. Bundled icons, one folder per category
        for folder, cat_name in categories:
            cat_dir = os.path.join(base_dir, folder)
            if os.path.isdir(cat_dir):
                self._scan_folder(cat_dir, cat_name)

        # 2. Persistent User Icons directory in ~/.printlabel/icons
        self._user_meta = self._load_user_meta()
        if os.path.isdir(self.user_dir):
            self._scan_folder(self.user_dir, USER_CATEGORY, user=True)

    def _scan_folder(self, folder_path: str, category_name: str, user: bool = False):
        for entry in sorted(os.scandir(folder_path), key=lambda e: e.name):
            if not (entry.is_file() and entry.name.lower().endswith(ICON_EXTENSIONS)):
                continue
            icon_id = os.path.splitext(entry.name)[0]
            meta = self._user_meta.get(entry.name, {}) if user else self._metadata.get(icon_id.lower(), {})

            title = meta.get("title") or icon_id.replace("_", " ").title()
            # Search also matches the title and file name, so the user's icons need no default words
            keywords = meta.get("keywords") or ([] if user else [icon_id.lower(), category_name.lower()])
            category = category_name
            if user and meta.get("category") in self.built_in_categories:
                category = meta["category"]

            if not any(item.file_path == entry.path for item in self._icons):
                self._icons.append(IconItem(
                    id=icon_id,
                    title=title,
                    category=category,
                    file_path=entry.path,
                    keywords=keywords,
                    user=user,
                ))

    def list_icons(self, category: str = ALL, search_query: str = "") -> List[IconItem]:
        """Filters icons by category (or Favourites / Recently used) and search keyword."""
        q = search_query.strip().lower()

        if category == RECENT:
            by_key = {icon.key: icon for icon in self._icons}
            pool = [by_key[k] for k in self.recent_keys() if k in by_key]
        elif category == FAVOURITES:
            favourites = set(self.favourite_keys())
            pool = [icon for icon in self._icons if icon.key in favourites]
        elif category == USER_CATEGORY:
            # My Icons holds all of the user's icons, whichever category they are filed under
            pool = [icon for icon in self._icons if icon.user]
        elif category != ALL:
            pool = [icon for icon in self._icons if icon.category == category]
        else:
            pool = list(self._icons)

        results = []
        for icon in pool:
            if q:
                matches = (
                    q in icon.id.lower()
                    or q in icon.title.lower()
                    or any(q in kw.lower() for kw in icon.keywords)
                )
                if not matches:
                    continue
            results.append(icon)

        # Recently used keeps its order (newest first); elsewhere built-in icons first, by title
        if category != RECENT:
            results.sort(key=lambda x: (x.user, x.title.lower()))
        return results

    def category_counts(self) -> Dict[str, int]:
        """Number of icons in each sidebar view."""
        return {view: len(self.list_icons(view)) for view in self.views}

    def get_icon_by_id(self, icon_id: str) -> Optional[IconItem]:
        for item in self._icons:
            if item.id.lower() == icon_id.lower():
                return item
        return None

    def get_icon_by_path(self, path: str) -> Optional[IconItem]:
        for item in self._icons:
            if os.path.normcase(item.file_path) == os.path.normcase(path):
                return item
        return None

    # --- Favourites and recently used (kept in config.json) ---

    def favourite_keys(self) -> List[str]:
        return list(config_manager.get("icon_favourites", []) or [])

    def set_favourite_keys(self, keys: List[str]):
        config_manager.set("icon_favourites", list(keys))

    def is_favourite(self, icon: IconItem) -> bool:
        return icon.key in self.favourite_keys()

    def toggle_favourite(self, icon: IconItem) -> bool:
        """Adds or removes a favourite; returns True if the icon is now a favourite."""
        keys = self.favourite_keys()
        if icon.key in keys:
            keys.remove(icon.key)
        else:
            keys.append(icon.key)
        config_manager.set("icon_favourites", keys)
        return icon.key in keys

    def recent_keys(self) -> List[str]:
        return list(config_manager.get("icon_recent", []) or [])

    def mark_used(self, icon: IconItem):
        """Puts an inserted icon at the front of Recently used."""
        keys = [k for k in self.recent_keys() if k != icon.key]
        config_manager.set("icon_recent", ([icon.key] + keys)[:RECENT_LIMIT])

    # --- The user's own icons ---

    def _load_user_meta(self) -> Dict[str, Dict[str, Any]]:
        try:
            with open(os.path.join(self.user_dir, USER_META_FILE), encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def notify_changed(self):
        """Tells the listeners that the user's icons changed."""
        for listener in list(self.change_listeners):
            try:
                listener()
            except Exception as e:
                print(f"Warning: after the icons changed: {e}", file=sys.stderr)

    def user_icons(self) -> List[IconItem]:
        return [icon for icon in self._icons if icon.user]

    def user_meta(self, icon: IconItem) -> Dict[str, Any]:
        """Everything kept about one of the user's icons: title, category, search words, editor settings."""
        return dict(self._user_meta.get(os.path.basename(icon.file_path), {}))

    def _save_user_meta(self):
        os.makedirs(self.user_dir, exist_ok=True)
        path = os.path.join(self.user_dir, USER_META_FILE)
        tmp_path = path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(self._user_meta, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, path)

    def update_user_icon(
        self, icon: IconItem, title: str, category: str, keywords: List[str]
    ) -> Optional[IconItem]:
        """Changes a user icon's title, category and search words. Built-in icons are left alone."""
        if not icon.user:
            return icon
        name = os.path.basename(icon.file_path)
        # Anything else kept about the icon, such as its editor settings, stays
        self._user_meta[name] = dict(self._user_meta.get(name, {}))
        self._user_meta[name].update({
            "title": title.strip() or icon.id.replace("_", " ").title(),
            "category": category if category in self.built_in_categories else USER_CATEGORY,
            "keywords": keywords,
        })
        self._save_user_meta()
        self.reload()
        self.notify_changed()
        return self.get_icon_by_path(icon.file_path)

    def delete_user_icon(self, icon: IconItem) -> bool:
        """Deletes one of the user's icons and forgets it in favourites and recently used."""
        if not icon.user:
            return False
        try:
            os.remove(icon.file_path)
        except OSError:
            return False
        if self._user_meta.pop(os.path.basename(icon.file_path), None) is not None:
            self._save_user_meta()
        for path in self.original_paths(icon.file_path):
            try:
                os.remove(path)
            except OSError:
                pass
        for config_key in ("icon_favourites", "icon_recent"):
            keys = list(config_manager.get(config_key, []) or [])
            if icon.key in keys:
                keys.remove(icon.key)
                config_manager.set(config_key, keys)
        self.reload()
        self.notify_changed()
        return True

    def original_paths(self, icon_file: str) -> Tuple[str, str]:
        """Where the original picture and the touch-ups of a user icon are kept."""
        stem = os.path.splitext(os.path.basename(icon_file))[0]
        folder = os.path.join(self.user_dir, ORIGINALS_DIR)
        return os.path.join(folder, f"{stem}.png"), os.path.join(folder, stem + TOUCH_SUFFIX)

    def _store_edit(
        self, icon_file: str, original: Optional[Image.Image], edit: Optional[IconEdit], touch: Optional[Image.Image]
    ) -> Dict[str, Any]:
        """Saves the original and touch-ups next to the icon; returns what goes in its metadata."""
        original_path, touch_path = self.original_paths(icon_file)
        if original is None or edit is None:
            for path in (original_path, touch_path):
                if os.path.isfile(path):
                    os.remove(path)
            return {}
        os.makedirs(os.path.dirname(original_path), exist_ok=True)
        prepare_original(original).save(original_path, "PNG")
        if touch is not None and touch.getbbox():
            touch.convert("L").save(touch_path, "PNG")
        elif os.path.isfile(touch_path):
            os.remove(touch_path)
        return {"edit": edit.to_dict()}

    def free_icon_path(self, name: str) -> str:
        """A file in the user's icons folder for a new icon called `name`, not used by any icon yet."""
        safe_name = "".join(c for c in name.strip().replace(" ", "_") if c.isalnum() or c in ("_", "-")).strip("_")
        if not safe_name:
            safe_name = "custom_icon"
        user_dir = self.user_dir
        os.makedirs(user_dir, exist_ok=True)
        target_path = os.path.join(user_dir, f"{safe_name}.png")
        counter = 1
        while os.path.isfile(target_path):
            target_path = os.path.join(user_dir, f"{safe_name}_{counter}.png")
            counter += 1
        return target_path

    def set_user_meta(self, file_name: str, meta: Dict[str, Any]):
        """Stores what is kept about one user icon, without reloading (used when restoring a backup)."""
        self._user_meta[file_name] = dict(meta)
        self._save_user_meta()

    def save_user_icon(
        self,
        image: Image.Image,
        name: str,
        category: str = USER_CATEGORY,
        keywords: Optional[List[str]] = None,
        original: Optional[Image.Image] = None,
        edit: Optional[IconEdit] = None,
        touch: Optional[Image.Image] = None,
    ) -> IconItem:
        """
        Saves a new icon into the user's icons folder. With an original picture and the
        settings that made the icon, the icon can be opened in the editor again later.
        """
        target_path = self.free_icon_path(name)
        safe_name = os.path.splitext(os.path.basename(target_path))[0]
        image.save(target_path, "PNG")
        meta = {
            "title": name.strip() or safe_name.replace("_", " ").title(),
            "category": category if category in self.built_in_categories else USER_CATEGORY,
            "keywords": list(keywords or []),
        }
        meta.update(self._store_edit(target_path, original, edit, touch))
        self._user_meta[os.path.basename(target_path)] = meta
        self._save_user_meta()
        self.reload()
        self.notify_changed()

        item = self.get_icon_by_path(target_path)
        if item:
            return item

        # Fallback return
        return IconItem(
            id=os.path.splitext(os.path.basename(target_path))[0],
            title=meta["title"],
            category=USER_CATEGORY,
            file_path=target_path,
            keywords=meta["keywords"],
            user=True,
        )

    def replace_user_icon(
        self,
        icon: IconItem,
        image: Image.Image,
        title: str,
        category: str,
        keywords: List[str],
        original: Optional[Image.Image] = None,
        edit: Optional[IconEdit] = None,
        touch: Optional[Image.Image] = None,
    ) -> Optional[IconItem]:
        """
        Saves an edited icon over one of the user's icons. The file name stays, so labels,
        favourites and recently used keep pointing at it.
        """
        if not icon.user:
            return None
        image.save(icon.file_path, "PNG")
        meta = {
            "title": title.strip() or icon.id.replace("_", " ").title(),
            "category": category if category in self.built_in_categories else USER_CATEGORY,
            "keywords": list(keywords),
        }
        meta.update(self._store_edit(icon.file_path, original, edit, touch))
        self._user_meta[os.path.basename(icon.file_path)] = meta
        self._save_user_meta()
        self.reload()
        self.notify_changed()
        return self.get_icon_by_path(icon.file_path)

    def edit_source(self, icon: IconItem) -> Tuple[Image.Image, Optional[IconEdit], Optional[Image.Image]]:
        """
        What the editor needs to open an icon again: the original picture, its settings and
        touch-ups. Built-in icons and icons saved before originals were kept open from the
        icon itself, with no settings.
        """
        if icon.user:
            meta = self._user_meta.get(os.path.basename(icon.file_path), {})
            original_path, touch_path = self.original_paths(icon.file_path)
            if meta.get("edit") and os.path.isfile(original_path):
                try:
                    with Image.open(original_path) as src:
                        original = src.convert("RGBA")
                    touch = None
                    if os.path.isfile(touch_path):
                        with Image.open(touch_path) as src:
                            touch = src.convert("L")
                    return original, IconEdit.from_dict(meta["edit"]), touch
                except Exception:
                    pass
        with Image.open(icon.file_path) as src:
            return src.convert("RGBA"), None, None


# Global singleton
icon_manager = IconManager()
