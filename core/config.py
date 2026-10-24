#!/usr/bin/env python3
"""
Application configuration manager for Cube Labeler.
Persists settings (AI API keys, custom directories, defaults) to ~/.printlabel/config.json.
"""

import os
import sys
import json
from typing import Any, Callable, Dict, List, Optional

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


# Settings that belong to this PC or are secrets, so a backup never carries them to another one:
# API keys are encrypted for this Windows user, ports and the backup folder differ per PC
_LOCAL_KEYS = ("last_serial_port",)
_LOCAL_PREFIXES = ("icon_backup_",)
_LOCAL_SUFFIXES = ("_api_key", "_api_key_protected")


def is_local_setting(key: str) -> bool:
    return key in _LOCAL_KEYS or key.startswith(_LOCAL_PREFIXES) or key.endswith(_LOCAL_SUFFIXES)


class ConfigManager:
    """Manages persistent application settings in ~/.printlabel/config.json."""

    def __init__(self):
        self._config: Dict[str, Any] = dict(DEFAULT_CONFIG)
        # Called after every save, e.g. to write an automatic backup
        self.change_listeners: List[Callable[[], None]] = []
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
            self._changed()
        except Exception as e:
            print(f"Warning: could not save settings to {CONFIG_FILE}: {e}", file=sys.stderr)
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    def _changed(self):
        for listener in list(self.change_listeners):
            try:
                listener()
            except Exception as e:
                print(f"Warning: after the settings changed: {e}", file=sys.stderr)

    def backup_settings(self) -> Dict[str, Any]:
        """Every setting that may go in a backup, so settings added later are backed up too."""
        return {k: v for k, v in self._config.items() if not is_local_setting(k)}

    def restore_settings(self, data: Dict[str, Any]):
        """Takes over the settings from a backup; this PC's own settings and keys stay."""
        for key, value in data.items():
            if isinstance(key, str) and not is_local_setting(key):
                self._config[key] = value
        self.save()

    def get(self, key: str, default: Any = None) -> Any:
        return self._config.get(key, default)

    def set(self, key: str, value: Any):
        self._config[key] = value
        self.save()

    # --- AI picture services: one API key and model per service ---

    @property
    def ai_provider(self) -> str:
        return str(self._config.get("ai_provider") or "gemini")

    @ai_provider.setter
    def ai_provider(self, value: str):
        self._config["ai_provider"] = value
        self.save()

    def api_key(self, provider: str) -> str:
        # Encrypted key first, then a plain-text key (non-Windows), then e.g. GEMINI_API_KEY
        key = secret_store.unprotect(str(self._config.get(f"{provider}_api_key_protected") or "")) or ""
        if not key:
            key = str(self._config.get(f"{provider}_api_key") or "")
        if not key.strip():
            key = os.environ.get(f"{provider.upper()}_API_KEY", "")
        return key.strip()

    def set_api_key(self, provider: str, value: str):
        value = (value or "").strip()
        token = secret_store.protect(value) if value else None
        if token:
            self._config[f"{provider}_api_key_protected"] = token
            self._config[f"{provider}_api_key"] = ""
        else:
            self._config[f"{provider}_api_key_protected"] = ""
            self._config[f"{provider}_api_key"] = value
        self.save()

    def ai_model(self, provider: str) -> str:
        """The model chosen for a service, or "" for the service's default."""
        model = str(self._config.get(f"{provider}_model") or "").strip()
        if provider == "gemini" and model == _LEGACY_TEXT_MODEL_DEFAULT:
            return ""
        return model

    def set_ai_model(self, provider: str, value: str):
        self._config[f"{provider}_model"] = (value or "").strip()
        self.save()

    @property
    def gemini_api_key(self) -> str:
        return self.api_key("gemini")

    @gemini_api_key.setter
    def gemini_api_key(self, value: str):
        self.set_api_key("gemini", value)

    @property
    def gemini_model(self) -> str:
        return self.ai_model("gemini") or DEFAULT_GEMINI_IMAGE_MODEL

    @property
    def last_serial_port(self) -> str:
        return self._config.get("last_serial_port", "").strip()

    @last_serial_port.setter
    def last_serial_port(self, value: str):
        self._config["last_serial_port"] = value.strip()
        self.save()

    @property
    def user_templates_dir(self) -> str:
        path = os.path.join(CONFIG_DIR, "templates")
        os.makedirs(path, exist_ok=True)
        return path

    @property
    def user_icons_dir(self) -> str:
        path = os.path.join(CONFIG_DIR, "icons")
        os.makedirs(path, exist_ok=True)
        return path


# Global singleton instance
config_manager = ConfigManager()
