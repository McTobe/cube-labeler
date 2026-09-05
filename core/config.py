#!/usr/bin/env python3
"""
Application configuration manager for Brother PT-P300BT Label Studio.
Persists settings (Gemini API key, custom directories, defaults) to ~/.printlabel/config.json.
"""

import os
import json
from typing import Any, Dict, Optional

CONFIG_DIR = os.path.normpath(os.path.expanduser("~/.printlabel"))
CONFIG_FILE = os.path.normpath(os.path.join(CONFIG_DIR, "config.json"))

DEFAULT_CONFIG: Dict[str, Any] = {
    "gemini_api_key": "",
    "gemini_model": "gemini-2.5-flash",
    "last_used_category": "All",
    "auto_save_ai_icons": True,
    "last_serial_port": "",
}


class ConfigManager:
    """Manages persistent application settings in ~/.printlabel/config.json."""

    def __init__(self):
        self._config: Dict[str, Any] = dict(DEFAULT_CONFIG)
        self._load()

    def _load(self):
        try:
            if os.path.isfile(CONFIG_FILE):
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self._config.update(data)
        except Exception:
            pass

    def save(self):
        try:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self._config, f, indent=2)
        except Exception:
            pass

    def get(self, key: str, default: Any = None) -> Any:
        return self._config.get(key, default)

    def set(self, key: str, value: Any):
        self._config[key] = value
        self.save()

    @property
    def gemini_api_key(self) -> str:
        # Also check GEMINI_API_KEY environment variable if not configured
        key = self._config.get("gemini_api_key", "").strip()
        if not key:
            key = os.environ.get("GEMINI_API_KEY", "").strip()
        return key

    @gemini_api_key.setter
    def gemini_api_key(self, value: str):
        self._config["gemini_api_key"] = value.strip()
        self.save()

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
