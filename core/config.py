#!/usr/bin/env python3
"""
Application configuration manager for Cube Labeler.
Persists settings (Gemini API key, custom directories, defaults) to ~/.printlabel/config.json.
"""

import os
import sys
import json
from typing import Any, Dict, Optional

from core import secret_store

CONFIG_DIR = os.path.normpath(os.path.expanduser("~/.printlabel"))
CONFIG_FILE = os.path.normpath(os.path.join(CONFIG_DIR, "config.json"))

DEFAULT_GEMINI_IMAGE_MODEL = "gemini-3.1-flash-image"
# Older versions saved this text-only model as the default; it cannot generate images
_LEGACY_TEXT_MODEL_DEFAULT = "gemini-2.5-flash"

DEFAULT_CONFIG: Dict[str, Any] = {
    "gemini_api_key": "",
    "gemini_api_key_protected": "",
    "gemini_model": DEFAULT_GEMINI_IMAGE_MODEL,
    "last_serial_port": "",
    "label_language": "en",
}


class ConfigManager:
    """Manages persistent application settings in ~/.printlabel/config.json."""

    def __init__(self):
        self._config: Dict[str, Any] = dict(DEFAULT_CONFIG)
        self._load()
        self._migrate_plaintext_api_key()

    def _migrate_plaintext_api_key(self):
        """Moves a plain-text API key from older config files into encrypted storage."""
        plain = str(self._config.get("gemini_api_key") or "").strip()
        if plain and secret_store.is_supported():
            token = secret_store.protect(plain)
            if token:
                self._config["gemini_api_key_protected"] = token
                self._config["gemini_api_key"] = ""
                self.save()

    def _load(self):
        try:
            if os.path.isfile(CONFIG_FILE):
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self._config.update(data)
        except Exception as e:
            print(f"Warning: could not read settings from {CONFIG_FILE}: {e}", file=sys.stderr)

    def save(self):
        # Write to a temp file and swap it in, so a crash mid-write never corrupts config.json
        tmp_path = CONFIG_FILE + ".tmp"
        try:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self._config, f, indent=2)
            os.replace(tmp_path, CONFIG_FILE)
        except Exception as e:
            print(f"Warning: could not save settings to {CONFIG_FILE}: {e}", file=sys.stderr)
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    def get(self, key: str, default: Any = None) -> Any:
        return self._config.get(key, default)

    def set(self, key: str, value: Any):
        self._config[key] = value
        self.save()

    @property
    def gemini_api_key(self) -> str:
        # Encrypted key first, then a plain-text key (non-Windows), then GEMINI_API_KEY
        key = secret_store.unprotect(str(self._config.get("gemini_api_key_protected") or "")) or ""
        if not key:
            key = str(self._config.get("gemini_api_key") or "")
        if not key.strip():
            key = os.environ.get("GEMINI_API_KEY", "")
        return key.strip()

    @gemini_api_key.setter
    def gemini_api_key(self, value: str):
        value = (value or "").strip()
        token = secret_store.protect(value) if value else None
        if token:
            self._config["gemini_api_key_protected"] = token
            self._config["gemini_api_key"] = ""
        else:
            self._config["gemini_api_key_protected"] = ""
            self._config["gemini_api_key"] = value
        self.save()

    @property
    def gemini_model(self) -> str:
        model = str(self._config.get("gemini_model") or "").strip()
        if not model or model == _LEGACY_TEXT_MODEL_DEFAULT:
            return DEFAULT_GEMINI_IMAGE_MODEL
        return model

    @property
    def last_serial_port(self) -> str:
        return self._config.get("last_serial_port", "").strip()

    @last_serial_port.setter
    def last_serial_port(self, value: str):
        self._config["last_serial_port"] = value.strip()
        self.save()

    @property
    def user_icons_dir(self) -> str:
        path = os.path.join(CONFIG_DIR, "icons")
        os.makedirs(path, exist_ok=True)
        return path


# Global singleton instance
config_manager = ConfigManager()
