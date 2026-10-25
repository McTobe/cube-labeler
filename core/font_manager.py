#!/usr/bin/env python3
"""
Font discovery, management and caching for Brother PT-P300BT label designer.
"""

import os
import sys
from typing import Dict, List, Optional, Tuple
from PIL import ImageFont

DEFAULT_FALLBACK_FONTS = [
    "Arial",
    "Segoe UI",
    "Calibri",
    "Consolas",
    "Tahoma",
    "Verdana",
    "Trebuchet MS",
    "Impact",
    "Courier New",
    "Times New Roman",
    "Comic Sans MS",
]

# Tried in order when a requested font isn't installed. Liberation Sans and Arimo are
# metric-compatible with Arial, so labels keep roughly the same size off Windows.
SUBSTITUTE_FONTS = [
    "Arial",
    "Liberation Sans",
    "Arimo",
    "Helvetica",
    "DejaVu Sans",
    "Segoe UI",
    "Calibri",
]

FONT_EXTENSIONS = (".ttf", ".otf", ".ttc")


def system_font_dirs() -> List[str]:
    """Returns the font folders on macOS and Linux (Windows fonts come from the registry)."""
    home = os.path.expanduser("~")
    if sys.platform == "darwin":
        return [
            os.path.join(home, "Library", "Fonts"),
            "/Library/Fonts",
            "/System/Library/Fonts",
            "/System/Library/Fonts/Supplemental",
        ]
    data_home = os.environ.get("XDG_DATA_HOME") or os.path.join(home, ".local", "share")
    return [
        os.path.join(data_home, "fonts"),
        os.path.join(home, ".fonts"),
        "/usr/local/share/fonts",
        "/usr/share/fonts",
    ]


class FontManager:
    """Manages system fonts and custom TrueType / OpenType font files."""

    def __init__(self):
        self._font_cache: Dict[str, str] = {}  # font_display_name -> full_path
        self._loaded_fonts: Dict[str, ImageFont.FreeTypeFont] = {}  # (path, size) -> font
        self._scan_system_fonts()

    def _scan_system_fonts(self):
        """Finds installed fonts: the registry on Windows, the standard font folders elsewhere."""
        if sys.platform != "win32":
            for font_dir in system_font_dirs():
                self.scan_font_dir(font_dir)
            return

        fonts_dir = os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts")

        # 1. Windows Registry: machine-wide fonts, then fonts installed for the current user only
        import winreg
        user_fonts_dir = os.path.join(
            os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Windows", "Fonts"
        )
        for hive, base_dir in (
            (winreg.HKEY_LOCAL_MACHINE, fonts_dir),
            (winreg.HKEY_CURRENT_USER, user_fonts_dir),
        ):
            self._scan_registry_fonts(winreg, hive, base_dir)

        # 2. Check font directory directly for standard fonts if registry had gaps
        if os.path.isdir(fonts_dir):
            common_files = {
                "Arial": "arial.ttf",
                "Arial Bold": "arialbd.ttf",
                "Segoe UI": "segoeui.ttf",
                "Segoe UI Bold": "segoeuib.ttf",
                "Calibri": "calibri.ttf",
                "Calibri Bold": "calibrib.ttf",
                "Consolas": "consola.ttf",
                "Consolas Bold": "consolab.ttf",
                "Tahoma": "tahoma.ttf",
                "Tahoma Bold": "tahomabd.ttf",
                "Verdana": "verdana.ttf",
                "Verdana Bold": "verdanab.ttf",
                "Trebuchet MS": "trebuc.ttf",
                "Impact": "impact.ttf",
                "Courier New": "cour.ttf",
                "Times New Roman": "times.ttf",
            }
            for name, filename in common_files.items():
                p = os.path.join(fonts_dir, filename)
                if os.path.isfile(p) and name not in self._font_cache:
                    self._font_cache[name] = p

    def scan_font_dir(self, font_dir: str):
        """Adds every font file under font_dir, named by the family and style stored in the file."""
        if not os.path.isdir(font_dir):
            return
        for root, _, files in os.walk(font_dir):
            for filename in sorted(files):
                if not filename.lower().endswith(FONT_EXTENSIONS):
                    continue
                path = os.path.join(root, filename)
                try:
                    family, style = ImageFont.truetype(path, 10).getname()
                except Exception:
                    continue
                if not family:
                    continue
                name = family if style in (None, "", "Regular", "Book", "Normal", "Roman") else f"{family} {style}"
                if name not in self._font_cache:
                    self._font_cache[name] = path

    def _scan_registry_fonts(self, winreg, hive, base_dir: str):
        """Adds fonts listed under one registry hive, resolving relative paths against base_dir."""
        try:
            reg_key = winreg.OpenKey(hive, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts")
        except OSError:
            return
        try:
            count = winreg.QueryInfoKey(reg_key)[1]
            for i in range(count):
                try:
                    font_name, font_file, _ = winreg.EnumValue(reg_key, i)
                except OSError:
                    continue
                # Clean up name: "Arial (TrueType)" -> "Arial"
                clean_name = font_name
                for suffix in [" (TrueType)", " (OpenType)", " (All type)", " (PostScript)"]:
                    clean_name = clean_name.replace(suffix, "").strip()

                font_path = font_file if os.path.isabs(font_file) else os.path.join(base_dir, font_file)

                if os.path.isfile(font_path) and font_path.lower().endswith(('.ttf', '.otf', '.ttc')):
                    if clean_name not in self._font_cache:
                        self._font_cache[clean_name] = font_path
        finally:
            winreg.CloseKey(reg_key)

    def get_font_names(self) -> List[str]:
        """Returns sorted list of font display names, with common ones prioritized."""
        available = set(self._font_cache.keys())
        prioritized = [f for f in DEFAULT_FALLBACK_FONTS if f in available]
        others = sorted(list(available - set(prioritized)), key=lambda s: s.lower())
        return prioritized + others

    def load_user_fonts(self, folder: str) -> List[str]:
        """Registers every font file the user added (kept in `folder`); returns their names."""
        names = []
        if os.path.isdir(folder):
            for filename in sorted(os.listdir(folder)):
                if filename.lower().endswith(FONT_EXTENSIONS):
                    name = self.register_custom_font(os.path.join(folder, filename))
                    if name:
                        names.append(name)
        return names

    def add_user_font(self, file_path: str, folder: str) -> Optional[str]:
        """Copies a font file into the user's font folder and registers the copy."""
        try:
            ImageFont.truetype(file_path, 10)
        except Exception:
            return None
        os.makedirs(folder, exist_ok=True)
        target = os.path.join(folder, os.path.basename(file_path))
        if os.path.normcase(os.path.abspath(target)) != os.path.normcase(os.path.abspath(file_path)):
            with open(file_path, "rb") as src, open(target, "wb") as out:
                out.write(src.read())
        return self.register_custom_font(target)

    def register_custom_font(self, file_path: str) -> Optional[str]:
        """Registers a user-provided font file and returns its assigned display name."""
        if not os.path.isfile(file_path):
            return None
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        display_name = f"[Custom] {base_name}"
        self._font_cache[display_name] = file_path
        return display_name

    def resolve_font_path(self, font_identifier: str) -> str:
        """Resolves a display name or file path to a verified font path."""
        # 1. Direct path check
        if os.path.isfile(font_identifier):
            return font_identifier

        # 2. Check font cache
        if font_identifier in self._font_cache:
            return self._font_cache[font_identifier]

        # 3. Fuzzy search in cache
        norm = font_identifier.strip().lower()
        for name, path in self._font_cache.items():
            if name.lower() == norm:
                return path

        # 4. Fall back to Arial or a similar installed font
        for name in SUBSTITUTE_FONTS:
            if name in self._font_cache:
                return self._font_cache[name]
        fonts_dir = os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts")
        for fb in ["arial.ttf", "segoeui.ttf", "calibri.ttf"]:
            fb_path = os.path.join(fonts_dir, fb)
            if os.path.isfile(fb_path):
                return fb_path

        # 5. Let load_font fall back to Pillow's built-in font
        return "arial.ttf"

    def _cached_name(self, name: str) -> Optional[str]:
        """The font cache key matching name, ignoring case, or None."""
        if name in self._font_cache:
            return name
        norm = name.strip().lower()
        for cached in self._font_cache:
            if cached.lower() == norm:
                return cached
        return None

    def _family_name(self, font_identifier: str) -> Optional[str]:
        """The installed family a font name resolves to, including the substitute used when it is missing."""
        if os.path.isfile(font_identifier):
            return None
        name = self._cached_name(font_identifier)
        if name is not None:
            return name
        for substitute in SUBSTITUTE_FONTS:
            if substitute in self._font_cache:
                return substitute
        return None

    def load_styled_font(
        self, font_identifier: str, size: int, bold: bool = False, italic: bool = False
    ) -> Tuple[ImageFont.FreeTypeFont, bool, bool]:
        """
        Loads the font's own bold and/or italic file when one is installed.
        Returns (font, fake_bold, fake_italic): the styles the caller still has to fake.
        """
        if not bold and not italic:
            return self.load_font(font_identifier, size), False, False
        family = self._family_name(font_identifier)
        if family is not None:
            wanted = []
            if bold and italic:
                wanted.append((("Bold Italic", "BoldItalic", "Bold Oblique"), False, False))
            if bold:
                wanted.append((("Bold",), False, italic))
            if italic:
                wanted.append((("Italic", "Oblique"), bold, False))
            for styles, fake_bold, fake_italic in wanted:
                for style in styles:
                    name = self._cached_name(f"{family} {style}")
                    if name is not None:
                        return self.load_font(name, size), fake_bold, fake_italic
        return self.load_font(font_identifier, size), bold, italic

    def load_font(self, font_identifier: str, size: int) -> ImageFont.FreeTypeFont:
        """Loads and caches an ImageFont instance of the specified size."""
        resolved_path = self.resolve_font_path(font_identifier)
        cache_key = f"{resolved_path}::{size}"
        if cache_key in self._loaded_fonts:
            return self._loaded_fonts[cache_key]

        try:
            font = ImageFont.truetype(resolved_path, size, encoding="utf-8")
        except Exception:
            try:
                # Pillow's built-in font scales (Pillow 10.1+), so auto-fit still works with no fonts installed
                font = ImageFont.load_default(size)
            except TypeError:
                font = ImageFont.load_default()

        self._loaded_fonts[cache_key] = font
        return font


# Global singleton instance
font_manager = FontManager()
