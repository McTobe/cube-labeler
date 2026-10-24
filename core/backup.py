#!/usr/bin/env python3
"""
Backups of Cube Labeler: the user's icons, settings and saved templates in one file.

A backup is one .cubebackup file (a zip). It holds every user icon with its title, category,
search words, original picture and editor settings, so restored icons can still be edited;
all settings except this PC's own ones and the API keys; and every other file in the app's
data folder, such as saved templates, so data added in later versions is backed up too.
Older icon-only .cubeicons backups can still be restored.

Automatic backups go to a folder the user picks, for example a Google Drive, OneDrive or
Dropbox folder that their sync app uploads. Plain zipfile and PIL only, so the web version
can read and write the same files.
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
from typing import Any, BinaryIO, Dict, Iterable, List, Optional, Tuple

from PIL import Image

from core.config import CONFIG_DIR, config_manager
from core.icon_manager import TOUCH_SUFFIX, USER_CATEGORY, IconManager, icon_manager

BACKUP_EXTENSION = ".cubebackup"
OLD_ICON_EXTENSION = ".cubeicons"
FORMAT_NAME = "cube-labeler-backup"
FORMAT_VERSION = 2
OLD_ICON_FORMAT = "cube-labeler-icons"
MANIFEST = "manifest.json"

# Automatic backups are named with this prefix and the time, and only these are ever pruned
AUTO_PREFIX = "Cube Labeler backup "
AUTO_KEEP_DEFAULT = 10
# Changes this close together go into one automatic backup
AUTO_DELAY_SECONDS = 3.0

# What a backup may hold, so a broken or hostile file cannot fill the disk
MAX_ICONS = 5000
MAX_DATA_FILES = 2000
MAX_FILE_BYTES = 25 * 1024 * 1024

# Files in the app's data folder that are backed up another way, or never
CONFIG_NAME = "config.json"
SKIP_SUFFIXES = (".tmp", ".part")
TEMPLATES_FOLDER = "templates"
# Settings that change all the time without the user meaning to; they go in a backup, but
# never make a new automatic one on their own
VOLATILE_SETTINGS = ("icon_recent",)

# The parts of a backup that can be restored on their own
ICONS = "icons"
SETTINGS = "settings"
TEMPLATES = "templates"
ALL_PARTS = (ICONS, SETTINGS, TEMPLATES)

# What to do with a backed-up icon or template whose name is already used by a different one
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
    # None for an icon-only backup from an older version
    settings: Optional[Dict[str, Any]] = None
    # Other files of the app's data folder, by path inside it with "/" separators
    files: Dict[str, bytes] = field(default_factory=dict)

    @property
    def templates(self) -> Dict[str, bytes]:
        return {p: d for p, d in self.files.items() if p.startswith(TEMPLATES_FOLDER + "/")}

    @property
    def other_files(self) -> Dict[str, bytes]:
        return {p: d for p, d in self.files.items() if not p.startswith(TEMPLATES_FOLDER + "/")}

    @property
    def parts(self) -> List[str]:
        """What this backup can restore."""
        parts = [ICONS] if self.icons else []
        if self.settings is not None:
            parts.append(SETTINGS)
        if self.templates:
            parts.append(TEMPLATES)
        return parts


@dataclass
class ImportPlan:
    """How a backup lines up with what is already there."""

    new: List[BackupIcon] = field(default_factory=list)
    conflicts: List[BackupIcon] = field(default_factory=list)  # same file name, different picture
    unchanged: List[BackupIcon] = field(default_factory=list)  # already there, same picture
    new_templates: List[str] = field(default_factory=list)
    template_conflicts: List[str] = field(default_factory=list)
    unchanged_templates: List[str] = field(default_factory=list)


@dataclass
class ImportResult:
    added: int = 0
    replaced: int = 0
    skipped: int = 0
    unchanged: int = 0
    templates_added: int = 0
    templates_replaced: int = 0
    templates_skipped: int = 0
    settings_restored: bool = False


def template_title(path: str) -> str:
    """A template's name as the user sees it, from its path in a backup."""
    return os.path.splitext(path.split("/")[-1])[0]


def _read_file(path: str) -> Optional[bytes]:
    try:
        with open(path, "rb") as f:
            return f.read()
    except OSError:
        return None


# ----- Collecting what goes in a backup -----

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


def _data_files(data_dir: str, skip_dirs: Iterable[str]) -> Dict[str, bytes]:
    """Every other file in the app's data folder: templates now, whatever later versions keep there."""
    skip = {os.path.normcase(os.path.abspath(d)) for d in skip_dirs}
    files: Dict[str, bytes] = {}
    if not os.path.isdir(data_dir):
        return files
    for root, dirs, names in os.walk(data_dir):
        dirs[:] = sorted(d for d in dirs if not d.startswith(".")
                         and os.path.normcase(os.path.abspath(os.path.join(root, d))) not in skip)
        for name in sorted(names):
            path = os.path.join(root, name)
            rel = os.path.relpath(path, data_dir).replace(os.sep, "/")
            if rel == CONFIG_NAME or name.startswith(".") or name.endswith(SKIP_SUFFIXES):
                continue
            try:
                if os.path.getsize(path) > MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            data = _read_file(path)
            if data is not None and len(files) < MAX_DATA_FILES:
                files[rel] = data
    return files


def collect(manager: IconManager, config, data_dir: Optional[str] = None) -> Backup:
    """Everything a backup holds, read from this PC."""
    data_dir = data_dir or CONFIG_DIR
    return Backup(
        created=datetime.now().astimezone().isoformat(timespec="seconds"),
        icons=_icon_entries(manager),
        settings=config.backup_settings(),
        # Never the backup folder itself, should it be inside the data folder
        files=_data_files(data_dir, [d for d in (manager.user_dir, config.get("icon_backup_folder", "")) if d]),
    )


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


def digest(backup: Backup) -> str:
    """Fingerprint of what a backup holds, to skip automatic backups when nothing changed."""
    h = hashlib.sha256()
    for entry in backup.icons:
        h.update(json.dumps(_manifest_icon(entry), sort_keys=True).encode("utf-8"))
        for name, data in sorted(_members(entry).items()):
            h.update(name.encode("utf-8"))
            h.update(hashlib.sha256(data).digest())
    settings = {k: v for k, v in (backup.settings or {}).items() if k not in VOLATILE_SETTINGS}
    h.update(json.dumps(settings, sort_keys=True, default=str).encode("utf-8"))
    for name, data in sorted(backup.files.items()):
        h.update(name.encode("utf-8"))
        h.update(hashlib.sha256(data).digest())
    return h.hexdigest()


def write_backup(backup: Backup, out: BinaryIO):
    manifest = {
        "format": FORMAT_NAME,
        "version": FORMAT_VERSION,
        "created": backup.created,
        "icons": [_manifest_icon(e) for e in backup.icons],
        "settings": backup.settings or {},
        "files": sorted(backup.files),
    }
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(MANIFEST, json.dumps(manifest, indent=2, ensure_ascii=False, default=str))
        for entry in backup.icons:
            for name, data in _members(entry).items():
                zf.writestr(name, data)
        for name, data in sorted(backup.files.items()):
            zf.writestr(f"data/{name}", data)


def _write_file_safely(path: str, backup: Backup):
    """Written next to the target first, so a failed save never leaves half a file for a sync app."""
    tmp_path = path + ".part"
    try:
        with open(tmp_path, "wb") as f:
            write_backup(backup, f)
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise


def export_backup(manager: IconManager, path: str, config=None, data_dir: Optional[str] = None) -> Backup:
    """Saves a backup file of everything; returns what went in it."""
    backup = collect(manager, config or config_manager, data_dir)
    _write_file_safely(path, backup)
    return backup


# ----- Reading a backup -----

def _safe_file_name(name: Any) -> bool:
    return (
        isinstance(name, str)
        and name == os.path.basename(name)
        and "/" not in name and "\\" not in name
        and not name.startswith(".")
        and name.lower().endswith(".png")
        and len(name) <= 120
    )


def _safe_data_path(path: Any) -> bool:
    """A path inside the app's data folder that cannot point outside it or at what is restored another way."""
    if not isinstance(path, str) or not path or len(path) > 200 or "\\" in path or ":" in path:
        return False
    parts = path.split("/")
    if any(not p or p.startswith(".") or p in ("..",) for p in parts):
        return False
    if path == CONFIG_NAME or parts[0] == "icons" or path.endswith(SKIP_SUFFIXES):
        return False
    return True


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
        raise BackupError("This is not a Cube Labeler backup.")
    with zf:
        try:
            manifest = json.loads(_member(zf, MANIFEST, required=True).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise BackupError("The backup's list of contents is damaged.")
        if not isinstance(manifest, dict) or manifest.get("format") not in (FORMAT_NAME, OLD_ICON_FORMAT):
            raise BackupError("This is not a Cube Labeler backup.")
        if not isinstance(manifest.get("version"), int) or manifest["version"] > FORMAT_VERSION:
            raise BackupError("This backup was made by a newer version of Cube Labeler. Update the app to restore it.")
        listed = manifest.get("icons")
        if not isinstance(listed, list) or len(listed) > MAX_ICONS:
            raise BackupError("The backup's list of contents is damaged.")

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

        settings = None
        files: Dict[str, bytes] = {}
        if manifest["format"] == FORMAT_NAME:
            settings = manifest.get("settings") if isinstance(manifest.get("settings"), dict) else {}
            listed_files = manifest.get("files") if isinstance(manifest.get("files"), list) else []
            for path in listed_files[:MAX_DATA_FILES]:
                if not _safe_data_path(path):
                    continue
                data = _member(zf, f"data/{path}")
                if data is not None:
                    files[path] = data
    return Backup(created=str(manifest.get("created") or ""), icons=icons, settings=settings, files=files)


# ----- Restoring -----

def plan_import(manager: IconManager, backup: Backup, data_dir: Optional[str] = None) -> ImportPlan:
    data_dir = data_dir or CONFIG_DIR
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
    for path, data in sorted(backup.templates.items()):
        current = _read_file(os.path.join(data_dir, *path.split("/")))
        if current is None:
            plan.new_templates.append(path)
        elif current == data:
            plan.unchanged_templates.append(path)
        else:
            plan.template_conflicts.append(path)
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


def _free_data_path(data_dir: str, path: str) -> str:
    """A path next to `path` that is not used yet: "Name (2).json"."""
    stem, ext = os.path.splitext(path)
    counter = 2
    while os.path.exists(os.path.join(data_dir, *f"{stem} ({counter}){ext}".split("/"))):
        counter += 1
    return f"{stem} ({counter}){ext}"


def restore_backup(
    manager: IconManager,
    backup: Backup,
    on_conflict: str = SKIP,
    parts: Iterable[str] = ALL_PARTS,
    config=None,
    data_dir: Optional[str] = None,
) -> ImportResult:
    """
    Restores the chosen parts of a backup. Icons and templates are added to what is there;
    ones that are already there unchanged are left alone. Settings replace the current ones,
    except this PC's own settings and the API keys.
    """
    parts = set(parts) & set(backup.parts)
    config = config or config_manager
    data_dir = data_dir or CONFIG_DIR
    plan = plan_import(manager, backup, data_dir)
    result = ImportResult()

    if SETTINGS in parts:
        config.restore_settings(backup.settings or {})
        for path, data in backup.other_files.items():
            _write(os.path.join(data_dir, *path.split("/")), data)
        result.settings_restored = True

    if TEMPLATES in parts:
        templates = backup.templates
        for path in plan.new_templates:
            _write(os.path.join(data_dir, *path.split("/")), templates[path])
            result.templates_added += 1
        for path in plan.template_conflicts:
            if on_conflict == REPLACE:
                _write(os.path.join(data_dir, *path.split("/")), templates[path])
                result.templates_replaced += 1
            elif on_conflict == KEEP_BOTH:
                _write(os.path.join(data_dir, *_free_data_path(data_dir, path).split("/")), templates[path])
                result.templates_added += 1
            else:
                result.templates_skipped += 1

    if ICONS in parts:
        result.unchanged = len(plan.unchanged)
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

    if result.added or result.replaced or result.settings_restored:
        manager.reload()
        manager.notify_changed()
    return result


def import_backup(manager: IconManager, path: str, on_conflict: str = SKIP, **kwargs) -> ImportResult:
    with open(path, "rb") as f:
        return restore_backup(manager, read_backup(f), on_conflict, **kwargs)


# ----- Automatic backups -----

class AutoBackup:
    """
    Writes a backup to the chosen folder a moment after the icons, settings or templates
    change, and keeps only the newest few. Nothing is written when nothing changed.
    """

    def __init__(self, manager: IconManager, config, data_dir: Optional[str] = None,
                 delay: float = AUTO_DELAY_SECONDS):
        self._manager = manager
        self._config = config
        self._data_dir = data_dir
        self._delay = delay
        self._timer: Optional[threading.Timer] = None
        # Separate locks: writing a backup saves settings, which schedules a check again
        self._timer_lock = threading.Lock()
        self._write_lock = threading.Lock()
        manager.change_listeners.append(self.schedule)
        if hasattr(config, "change_listeners"):
            config.change_listeners.append(self.schedule)

    @property
    def folder(self) -> str:
        return str(self._config.get("icon_backup_folder", "") or "")

    @folder.setter
    def folder(self, value: str):
        self._config.set("icon_backup_folder", value or "")
        # A new folder gets a backup even if nothing changed
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
        with self._timer_lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self._delay, self._run_quietly)
            self._timer.daemon = True
            self._timer.start()

    def flush(self):
        """Writes a scheduled backup now, e.g. when the app closes."""
        with self._timer_lock:
            timer, self._timer = self._timer, None
        if timer is not None:
            timer.cancel()
            self._run_quietly()

    def _run_quietly(self):
        try:
            self.backup_now()
        except Exception as e:
            print(f"Warning: automatic backup failed: {e}", file=sys.stderr)

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
        with self._write_lock:
            backup = collect(self._manager, self._config, self._data_dir)
            fingerprint = digest(backup)
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
                _write_file_safely(path, backup)
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


# The app's automatic backup, following the global icon library and settings
auto_backup = AutoBackup(icon_manager, config_manager)
atexit.register(auto_backup.flush)
