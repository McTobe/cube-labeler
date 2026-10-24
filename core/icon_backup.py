#!/usr/bin/env python3
"""
Backups of the user's own icons for Cube Labeler.

A backup is one .cubeicons file (a zip) holding every user icon with its title, category,
search words, favourite mark, original picture and editor settings, so restored icons can
still be edited. Automatic backups go to a folder the user picks, for example a Google
Drive, OneDrive or Dropbox folder that their sync app uploads. Plain zipfile and PIL only,
so the web version can read and write the same files.
"""

import atexit
import hashlib
import io
import json
import os
import string
import sys
import threading
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, BinaryIO, Dict, List, Optional, Tuple

from PIL import Image

from core.config import config_manager
from core.icon_manager import TOUCH_SUFFIX, USER_CATEGORY, IconManager, icon_manager

BACKUP_EXTENSION = ".cubeicons"
FORMAT_NAME = "cube-labeler-icons"
FORMAT_VERSION = 1
MANIFEST = "manifest.json"

# Automatic backups are named with this prefix and the time, and only these are ever pruned
AUTO_PREFIX = "Cube Labeler icons "
AUTO_KEEP_DEFAULT = 10
# Changes this close together go into one automatic backup
AUTO_DELAY_SECONDS = 3.0

# What a backup may hold, so a broken or hostile file cannot fill the disk
MAX_ICONS = 5000
MAX_FILE_BYTES = 25 * 1024 * 1024

# What to do with a backed-up icon whose file name is already used by another icon
SKIP = "skip"
REPLACE = "replace"
KEEP_BOTH = "keep_both"


class BackupError(Exception):
    """The file is not a backup this version can read."""


@dataclass
class BackupIcon:
    file: str
    meta: Dict[str, Any]
    favourite: bool
    icon: bytes
    original: Optional[bytes] = None
    touch: Optional[bytes] = None

    @property
    def title(self) -> str:
        return str(self.meta.get("title") or os.path.splitext(self.file)[0].replace("_", " ").title())


@dataclass
class Backup:
    created: str
    icons: List[BackupIcon]


@dataclass
class ImportPlan:
    """How a backup lines up with the icons already there."""

    new: List[BackupIcon] = field(default_factory=list)
    conflicts: List[BackupIcon] = field(default_factory=list)  # same file name, different picture
    unchanged: List[BackupIcon] = field(default_factory=list)  # already there, same picture


@dataclass
class ImportResult:
    added: int = 0
    replaced: int = 0
    skipped: int = 0
    unchanged: int = 0


def _read_file(path: str) -> Optional[bytes]:
    try:
        with open(path, "rb") as f:
            return f.read()
    except OSError:
        return None


def _icon_entries(manager: IconManager) -> List[BackupIcon]:
    favourites = set(manager.favourite_keys())
    entries = []
    for icon in sorted(manager.user_icons(), key=lambda i: os.path.basename(i.file_path).lower()):
        data = _read_file(icon.file_path)
        if data is None:
            continue
        meta = manager.user_meta(icon)
        original_path, touch_path = manager.original_paths(icon.file_path)
        original = _read_file(original_path) if meta.get("edit") else None
        if original is None:
            meta.pop("edit", None)
        entries.append(BackupIcon(
            file=os.path.basename(icon.file_path),
            meta=meta,
            favourite=icon.key in favourites,
            icon=data,
            original=original,
            touch=_read_file(touch_path) if original is not None else None,
        ))
    return entries


def _members(entry: BackupIcon) -> Dict[str, bytes]:
    stem = os.path.splitext(entry.file)[0]
    files = {f"icons/{entry.file}": entry.icon}
    if entry.original is not None:
        files[f"originals/{stem}.png"] = entry.original
    if entry.touch is not None:
        files[f"originals/{stem}{TOUCH_SUFFIX}"] = entry.touch
    return files


def _manifest_icon(entry: BackupIcon) -> Dict[str, Any]:
    return {"file": entry.file, "favourite": entry.favourite, "meta": entry.meta}


def digest(entries: List[BackupIcon]) -> str:
    """Fingerprint of the icons' content, to skip automatic backups when nothing changed."""
    h = hashlib.sha256()
    for entry in entries:
        h.update(json.dumps(_manifest_icon(entry), sort_keys=True).encode("utf-8"))
        for name, data in sorted(_members(entry).items()):
            h.update(name.encode("utf-8"))
            h.update(hashlib.sha256(data).digest())
    return h.hexdigest()


def write_backup(manager: IconManager, out: BinaryIO, entries: Optional[List[BackupIcon]] = None) -> int:
    """Writes all of the user's icons to `out` as a backup; returns how many icons it holds."""
    if entries is None:
        entries = _icon_entries(manager)
    manifest = {
        "format": FORMAT_NAME,
        "version": FORMAT_VERSION,
        "created": datetime.now().astimezone().isoformat(timespec="seconds"),
        "icons": [_manifest_icon(e) for e in entries],
    }
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(MANIFEST, json.dumps(manifest, indent=2, ensure_ascii=False))
        for entry in entries:
            for name, data in _members(entry).items():
                zf.writestr(name, data)
    return len(entries)


def export_backup(manager: IconManager, path: str) -> int:
    """Saves a backup file; written next to it first, so a failed save never leaves half a file."""
    tmp_path = path + ".part"
    try:
        with open(tmp_path, "wb") as f:
            count = write_backup(manager, f)
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise
    return count


def _safe_file_name(name: Any) -> bool:
    return (
        isinstance(name, str)
        and name == os.path.basename(name)
        and "/" not in name and "\\" not in name
        and not name.startswith(".")
        and name.lower().endswith(".png")
        and len(name) <= 120
    )


def _member(zf: zipfile.ZipFile, name: str, required: bool = False) -> Optional[bytes]:
    try:
        info = zf.getinfo(name)
    except KeyError:
        if required:
            raise BackupError(f"The backup is missing {name}.")
        return None
    if info.file_size > MAX_FILE_BYTES:
        raise BackupError(f"{name} in the backup is too large.")
    return zf.read(info)


def _check_png(data: bytes, name: str):
    try:
        with Image.open(io.BytesIO(data)) as img:
            if img.format != "PNG":
                raise BackupError(f"{name} in the backup is not a PNG picture.")
            img.verify()
    except BackupError:
        raise
    except Exception:
        raise BackupError(f"{name} in the backup is not a readable picture.")


def read_backup(source: BinaryIO) -> Backup:
    """Reads and checks a backup file. Raises BackupError when it is not a usable backup."""
    try:
        zf = zipfile.ZipFile(source)
    except (zipfile.BadZipFile, OSError):
        raise BackupError("This is not a Cube Labeler icon backup.")
    with zf:
        try:
            manifest = json.loads(_member(zf, MANIFEST, required=True).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise BackupError("The backup's list of icons is damaged.")
        if not isinstance(manifest, dict) or manifest.get("format") != FORMAT_NAME:
            raise BackupError("This is not a Cube Labeler icon backup.")
        if not isinstance(manifest.get("version"), int) or manifest["version"] > FORMAT_VERSION:
            raise BackupError("This backup was made by a newer version of Cube Labeler. Update the app to restore it.")
        listed = manifest.get("icons")
        if not isinstance(listed, list) or len(listed) > MAX_ICONS:
            raise BackupError("The backup's list of icons is damaged.")

        icons: List[BackupIcon] = []
        seen = set()
        for item in listed:
            if not isinstance(item, dict) or not _safe_file_name(item.get("file")):
                continue
            file = item["file"]
            if file.lower() in seen:
                continue
            seen.add(file.lower())
            stem = os.path.splitext(file)[0]
            data = _member(zf, f"icons/{file}", required=True)
            _check_png(data, file)
            meta = item.get("meta") if isinstance(item.get("meta"), dict) else {}
            original = _member(zf, f"originals/{stem}.png")
            touch = _member(zf, f"originals/{stem}{TOUCH_SUFFIX}") if original is not None else None
            if original is not None:
                _check_png(original, f"The original of {file}")
            if touch is not None:
                _check_png(touch, f"The touch-ups of {file}")
            if original is None:
                meta.pop("edit", None)
            icons.append(BackupIcon(file=file, meta=meta, favourite=bool(item.get("favourite")),
                                    icon=data, original=original, touch=touch))
    return Backup(created=str(manifest.get("created") or ""), icons=icons)


def plan_import(manager: IconManager, backup: Backup) -> ImportPlan:
    existing = {os.path.basename(i.file_path).lower(): i for i in manager.user_icons()}
    plan = ImportPlan()
    for entry in backup.icons:
        icon = existing.get(entry.file.lower())
        if icon is None:
            plan.new.append(entry)
        elif _read_file(icon.file_path) == entry.icon:
            plan.unchanged.append(entry)
        else:
            plan.conflicts.append(entry)
    return plan


def _write(path: str, data: Optional[bytes]):
    if data is None:
        if os.path.isfile(path):
            os.remove(path)
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


def _restore_one(manager: IconManager, entry: BackupIcon, target: str, favourites: List[str]):
    _write(target, entry.icon)
    original_path, touch_path = manager.original_paths(target)
    _write(original_path, entry.original)
    _write(touch_path, entry.touch)
    meta = dict(entry.meta)
    meta["title"] = entry.title
    if meta.get("category") not in manager.built_in_categories:
        meta["category"] = USER_CATEGORY
    if not isinstance(meta.get("keywords"), list):
        meta["keywords"] = []
    manager.set_user_meta(os.path.basename(target), meta)
    key = f"user/{os.path.basename(target)}"
    if entry.favourite and key not in favourites:
        favourites.append(key)


def restore_backup(manager: IconManager, backup: Backup, on_conflict: str = SKIP) -> ImportResult:
    """Adds the backup's icons to the user's icons. Icons already there with the same picture are left alone."""
    plan = plan_import(manager, backup)
    result = ImportResult(unchanged=len(plan.unchanged))
    favourites = manager.favourite_keys()
    before = list(favourites)

    for entry in plan.new:
        _restore_one(manager, entry, os.path.join(manager.user_dir, entry.file), favourites)
        result.added += 1
    for entry in plan.conflicts:
        if on_conflict == REPLACE:
            _restore_one(manager, entry, os.path.join(manager.user_dir, entry.file), favourites)
            result.replaced += 1
        elif on_conflict == KEEP_BOTH:
            _restore_one(manager, entry, manager.free_icon_path(os.path.splitext(entry.file)[0]), favourites)
            result.added += 1
        else:
            result.skipped += 1

    if favourites != before:
        manager.set_favourite_keys(favourites)
    if result.added or result.replaced:
        manager.reload()
        manager.notify_changed()
    return result


def import_backup(manager: IconManager, path: str, on_conflict: str = SKIP) -> ImportResult:
    with open(path, "rb") as f:
        return restore_backup(manager, read_backup(f), on_conflict)


class AutoBackup:
    """
    Writes a backup to the chosen folder a moment after the user's icons change, and keeps
    only the newest few. Nothing is written when the icons are the same as in the last one.
    """

    def __init__(self, manager: IconManager, config, delay: float = AUTO_DELAY_SECONDS):
        self._manager = manager
        self._config = config
        self._delay = delay
        self._timer: Optional[threading.Timer] = None
        self._lock = threading.Lock()
        manager.change_listeners.append(self.schedule)

    @property
    def folder(self) -> str:
        return str(self._config.get("icon_backup_folder", "") or "")

    @folder.setter
    def folder(self, value: str):
        self._config.set("icon_backup_folder", value or "")
        # A new folder gets a backup even if the icons did not change
        self._config.set("icon_backup_digest", "")

    @property
    def keep(self) -> int:
        try:
            return max(1, int(self._config.get("icon_backup_keep", AUTO_KEEP_DEFAULT)))
        except (TypeError, ValueError):
            return AUTO_KEEP_DEFAULT

    @property
    def last_backup(self) -> str:
        return str(self._config.get("icon_backup_last", "") or "")

    @property
    def last_error(self) -> str:
        return str(self._config.get("icon_backup_error", "") or "")

    def schedule(self):
        """Backs up after a short wait, so several changes in a row make one backup."""
        if not self.folder:
            return
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self._delay, self._run_quietly)
            self._timer.daemon = True
            self._timer.start()

    def flush(self):
        """Writes a scheduled backup now, e.g. when the app closes."""
        with self._lock:
            timer, self._timer = self._timer, None
        if timer is not None:
            timer.cancel()
            self._run_quietly()

    def _run_quietly(self):
        try:
            self.backup_now()
        except Exception as e:
            print(f"Warning: automatic icon backup failed: {e}", file=sys.stderr)

    def backups(self) -> List[str]:
        """The automatic backups in the folder, newest first."""
        folder = self.folder
        try:
            names = [n for n in os.listdir(folder) if n.startswith(AUTO_PREFIX) and n.endswith(BACKUP_EXTENSION)]
        except OSError:
            return []
        paths = [os.path.join(folder, n) for n in names]

        def written(path: str):
            try:
                return os.stat(path).st_mtime_ns, path
            except OSError:
                return 0, path

        return sorted(paths, key=written, reverse=True)

    def backup_now(self, force: bool = False) -> Optional[str]:
        """Writes a backup to the folder and prunes old ones; returns its path, or None when skipped."""
        folder = self.folder
        if not folder:
            return None
        with self._lock:
            entries = _icon_entries(self._manager)
            if not entries:
                return None
            fingerprint = digest(entries)
            if not force and fingerprint == self._config.get("icon_backup_digest", ""):
                return None
            try:
                if not os.path.isdir(folder):
                    raise OSError(f"The backup folder {folder} is not there.")
                stamp = datetime.now().strftime("%Y-%m-%d %H%M%S")
                path = os.path.join(folder, f"{AUTO_PREFIX}{stamp}{BACKUP_EXTENSION}")
                counter = 2
                while os.path.exists(path):
                    path = os.path.join(folder, f"{AUTO_PREFIX}{stamp}-{counter}{BACKUP_EXTENSION}")
                    counter += 1
                tmp_path = path + ".part"
                try:
                    with open(tmp_path, "wb") as f:
                        write_backup(self._manager, f, entries)
                    os.replace(tmp_path, path)
                except OSError:
                    try:
                        os.remove(tmp_path)
                    except OSError:
                        pass
                    raise
            except OSError as e:
                self._config.set("icon_backup_error", str(e))
                raise
            self._config.set("icon_backup_digest", fingerprint)
            self._config.set("icon_backup_last", datetime.now().isoformat(timespec="seconds"))
            self._config.set("icon_backup_error", "")
        for old in self.backups()[self.keep:]:
            try:
                os.remove(old)
            except OSError:
                pass
        return path


def cloud_folders() -> List[Tuple[str, str]]:
    """Folders that a cloud sync app keeps in step, found on this computer: (name, path)."""
    home = os.path.expanduser("~")
    found: List[Tuple[str, str]] = []

    def add(name: str, path: Optional[str]):
        # One folder per service, the first one found
        if path and os.path.isdir(path) and all(n != name for n, _ in found):
            found.append((name, os.path.normpath(path)))

    # Google Drive for desktop shows up as its own drive letter, named in the Windows language
    drive_names = ("My Drive", "Min enhet", "Meine Ablage", "Mon Drive", "Mi unidad")
    if sys.platform == "win32":
        for letter in string.ascii_uppercase[3:]:
            for name in drive_names:
                add("Google Drive", f"{letter}:\\{name}")
    for name in drive_names:
        add("Google Drive", os.path.join(home, "Google Drive", name))
    add("Google Drive", os.path.join(home, "Google Drive"))
    for var in ("OneDriveConsumer", "OneDrive", "OneDriveCommercial"):
        add("OneDrive", os.environ.get(var))
    add("OneDrive", os.path.join(home, "OneDrive"))
    add("Dropbox", os.path.join(home, "Dropbox"))
    add("iCloud Drive", os.path.join(home, "iCloudDrive"))
    return found


# The app's automatic backup, following the global icon library
auto_backup = AutoBackup(icon_manager, config_manager)
atexit.register(auto_backup.flush)
