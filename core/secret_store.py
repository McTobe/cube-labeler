#!/usr/bin/env python3
"""
Encrypts small secrets (such as the Gemini API key) for the current Windows user with DPAPI,
so they are not stored as plain text in config.json. Other platforms are not supported and
callers fall back to plain-text storage.
"""

import base64
import ctypes
import sys
from typing import Optional

CRYPTPROTECT_UI_FORBIDDEN = 0x01


def is_supported() -> bool:
    return sys.platform == "win32"


if is_supported():
    from ctypes import wintypes

    class _DataBlob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    _crypt32 = ctypes.windll.crypt32
    _kernel32 = ctypes.windll.kernel32

    def _run(func, data: bytes) -> bytes:
        buf = ctypes.create_string_buffer(data, len(data))
        blob_in = _DataBlob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
        blob_out = _DataBlob()
        if not func(ctypes.byref(blob_in), None, None, None, None,
                    CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(blob_out)):
            raise ctypes.WinError()
        try:
            return ctypes.string_at(blob_out.pbData, blob_out.cbData)
        finally:
            _kernel32.LocalFree(blob_out.pbData)


def protect(secret: str) -> Optional[str]:
    """Returns the secret encrypted for the current user (base64), or None if unsupported/failed."""
    if not is_supported():
        return None
    try:
        return base64.b64encode(_run(_crypt32.CryptProtectData, secret.encode("utf-8"))).decode("ascii")
    except Exception:
        return None


def unprotect(token: str) -> Optional[str]:
    """Decrypts a value produced by protect(), or returns None if it cannot be decrypted."""
    if not is_supported() or not token:
        return None
    try:
        return _run(_crypt32.CryptUnprotectData, base64.b64decode(token)).decode("utf-8")
    except Exception:
        return None
