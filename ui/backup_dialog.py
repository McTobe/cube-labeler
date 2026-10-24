#!/usr/bin/env python3
"""
Backups window: export and restore a backup of the icons, settings and templates, and
automatic backups to a folder that a cloud sync app (Google Drive, OneDrive, Dropbox) uploads.
"""

import os
from datetime import datetime
from tkinter import filedialog, messagebox
from typing import Callable, Dict, Optional, Tuple

import customtkinter as ctk

from core import backup as bk
from core.backup import (
    BACKUP_EXTENSION, ICONS, KEEP_BOTH, OLD_ICON_EXTENSION, REPLACE, SETTINGS, SKIP, TEMPLATES,
    BackupError, auto_backup,
)
from core.icon_manager import icon_manager
from ui.widgets import MUTED_TEXT

ERROR_RED = "#DC2626"
OK_GREEN = ("#047857", "#34D399")
BACKUP_SUBFOLDER = "Cube Labeler backups"
FILE_TYPES = [
    ("Cube Labeler backups", f"*{BACKUP_EXTENSION} *{OLD_ICON_EXTENSION}"),
    ("All files", "*.*"),
]
CLASH_CHOICES = (("Keep both", KEEP_BOTH), ("Replace mine", REPLACE), ("Skip them", SKIP))


def _when(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return iso or "an unknown time"


def backup_place(folder: str) -> str:
    """Where automatic backups go, as the user knows it: the cloud service's name, or the folder's."""
    norm = os.path.normcase(os.path.normpath(folder))
    for name, path in bk.cloud_folders():
        root = os.path.normcase(os.path.normpath(path))
        if norm == root or norm.startswith(root + os.sep):
            return name
    return os.path.basename(os.path.normpath(folder)) or folder


def backup_status() -> Tuple[str, object, bool]:
    """A one-line status of automatic backup for the library and Settings: (text, colour, on)."""
    folder = auto_backup.folder
    if not folder:
        return "Auto-backup off", MUTED_TEXT, False
    place = backup_place(folder)
    if auto_backup.last_error:
        return f"● Auto-backup to {place} failed", ERROR_RED, True
    if auto_backup.last_backup:
        return f"● Auto-backup on: {place} · last {_when(auto_backup.last_backup)}", OK_GREEN, True
    return f"● Auto-backup on: {place}", OK_GREEN, True


class RestoreDialog(ctk.CTkToplevel):
    """Asks which parts of a backup to restore, and what to do with names already taken."""

    PART_LABELS = {ICONS: "Icons", SETTINGS: "Settings", TEMPLATES: "Templates"}

    def __init__(self, parent, backup: bk.Backup, plan: bk.ImportPlan):
        super().__init__(parent)
        self.choice: Optional[Tuple[set, str]] = None
        self.title("Restore backup")
        self.resizable(False, False)
        self.transient(parent)

        ctk.CTkLabel(self, text=f"Backup made {_when(backup.created)}", font=ctk.CTkFont(size=14, weight="bold"),
                     anchor="w").pack(fill="x", padx=16, pady=(16, 2))
        ctk.CTkLabel(self, text="Choose what to restore:", anchor="w", text_color=MUTED_TEXT).pack(
            fill="x", padx=16, pady=(0, 6))

        counts = {
            ICONS: f"{len(backup.icons)} icons" + (f", {len(plan.unchanged)} already here" if plan.unchanged else ""),
            SETTINGS: "replaces your settings; your API keys and this PC's printer and backup folder stay",
            TEMPLATES: f"{len(backup.templates)} templates"
                       + (f", {len(plan.unchanged_templates)} already here" if plan.unchanged_templates else ""),
        }
        self.part_vars: Dict[str, ctk.BooleanVar] = {}
        for part in backup.parts:
            var = ctk.BooleanVar(value=True)
            self.part_vars[part] = var
            ctk.CTkCheckBox(self, text=f"{self.PART_LABELS[part]}  ({counts[part]})", variable=var,
                            command=self._update).pack(anchor="w", padx=16, pady=2)

        clashes = [e.title for e in plan.conflicts] + [bk.template_title(p) for p in plan.template_conflicts]
        self.clash_var = ctk.StringVar(value=CLASH_CHOICES[0][0])
        self.clash_box = ctk.CTkFrame(self, fg_color="transparent")
        if clashes:
            self.clash_box.pack(fill="x", padx=16, pady=(10, 0))
            names = ", ".join(clashes[:6]) + (" …" if len(clashes) > 6 else "")
            what = "1 has" if len(clashes) == 1 else f"{len(clashes)} have"
            ctk.CTkLabel(self.clash_box, text=f"{what} the same name as one of yours, but differs: {names}",
                         anchor="w", justify="left", wraplength=440).pack(fill="x")
            ctk.CTkSegmentedButton(self.clash_box, values=[label for label, _ in CLASH_CHOICES],
                                   variable=self.clash_var).pack(anchor="w", pady=(4, 0))

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=16)
        self.btn_restore = ctk.CTkButton(row, text="Restore", width=110, command=self._restore)
        self.btn_restore.pack(side="right")
        ctk.CTkButton(row, text="Cancel", width=90, fg_color="gray30", hover_color="gray40",
                      command=self.destroy).pack(side="right", padx=8)
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self._update()
        self.after(50, self._grab)

    def _grab(self):
        try:
            self.grab_set()
            self.focus_force()
        except Exception:
            pass

    def _update(self):
        self.btn_restore.configure(state="normal" if any(v.get() for v in self.part_vars.values()) else "disabled")

    def _restore(self):
        parts = {part for part, var in self.part_vars.items() if var.get()}
        clash = next(choice for label, choice in CLASH_CHOICES if label == self.clash_var.get())
        self.choice = (parts, clash)
        self.destroy()


class BackupDialog(ctk.CTkToplevel):
    def __init__(self, parent, on_changed: Callable[[], None]):
        super().__init__(parent)
        self._on_changed = on_changed
        self.title("Backups")
        self.geometry("560x530")
        self.resizable(False, False)
        self.transient(parent)
        self._build()
        self._refresh_auto()
        self.after(50, self._grab)

    def _grab(self):
        try:
            self.grab_set()
            self.focus_force()
        except Exception:
            pass

    def _card(self, title: str, text: str) -> ctk.CTkFrame:
        card = ctk.CTkFrame(self, corner_radius=10)
        card.pack(fill="x", padx=16, pady=(0, 10))
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=14, pady=12)
        ctk.CTkLabel(inner, text=title, font=ctk.CTkFont(size=14, weight="bold"), anchor="w").pack(fill="x")
        ctk.CTkLabel(inner, text=text, anchor="w", justify="left", wraplength=500,
                     text_color=MUTED_TEXT).pack(fill="x", pady=(0, 8))
        return inner

    def _build(self):
        ctk.CTkLabel(self, text="Backups", font=ctk.CTkFont(size=18, weight="bold"), anchor="w").pack(
            fill="x", padx=16, pady=(14, 10))
        count = len(icon_manager.user_icons())
        files = self._card(
            "Backup file",
            f"One file with your icons ({count}), with their original pictures so they can still be edited, "
            "your saved templates and all settings. API keys are left out: paste them again after a restore.",
        )
        row = ctk.CTkFrame(files, fg_color="transparent")
        row.pack(fill="x")
        ctk.CTkButton(row, text="Export backup…", width=140, command=self._export).pack(side="left")
        ctk.CTkButton(row, text="Restore backup…", width=140, command=self._import).pack(side="left", padx=8)

        auto = self._card(
            "Automatic backup",
            "Pick a folder that your cloud app syncs, like Google Drive, OneDrive or Dropbox. "
            f"A backup is saved there a few seconds after something changes, and the newest {auto_backup.keep} are kept.",
        )
        self.lbl_folder = ctk.CTkLabel(auto, text="", anchor="w", justify="left", wraplength=500)
        self.lbl_folder.pack(fill="x")
        self.lbl_status = ctk.CTkLabel(auto, text="", anchor="w", justify="left", wraplength=500,
                                       font=ctk.CTkFont(size=11))
        self.lbl_status.pack(fill="x", pady=(0, 6))
        clouds = bk.cloud_folders()[:3]
        if clouds:
            found = "Found on this PC: " + ", ".join(name for name, _ in clouds) + \
                f". Pick one to save backups in a “{BACKUP_SUBFOLDER}” folder there."
        else:
            found = ("No Google Drive, OneDrive, Dropbox or iCloud Drive folder found on this PC. "
                     "Choose any folder, for example one your cloud app syncs.")
        self.lbl_clouds = ctk.CTkLabel(auto, text=found, anchor="w", justify="left", wraplength=500,
                                       font=ctk.CTkFont(size=11), text_color=MUTED_TEXT)
        self.lbl_clouds.pack(fill="x", pady=(0, 4))
        self.cloud_row = ctk.CTkFrame(auto, fg_color="transparent")
        self.cloud_row.pack(fill="x", pady=(0, 6))
        for name, path in clouds:
            ctk.CTkButton(self.cloud_row, text=f"Use {name}", width=130, fg_color="#8B5CF6", hover_color="#7C3AED",
                          command=lambda p=path: self._use_folder(os.path.join(p, BACKUP_SUBFOLDER))
                          ).pack(side="left", padx=(0, 8))
        actions = ctk.CTkFrame(auto, fg_color="transparent")
        actions.pack(fill="x")
        ctk.CTkButton(actions, text="Choose folder…", width=130, command=self._choose_folder).pack(side="left")
        self.btn_now = ctk.CTkButton(actions, text="Back up now", width=110, command=self._backup_now)
        self.btn_now.pack(side="left", padx=8)
        self.btn_off = ctk.CTkButton(actions, text="Turn off", width=90, fg_color="gray30", hover_color="gray40",
                                     command=lambda: self._use_folder(""))
        self.btn_off.pack(side="left")

        ctk.CTkButton(self, text="Close", width=100, fg_color="gray30", hover_color="gray40",
                      command=self.destroy).pack(side="right", padx=16, pady=(4, 14))

    # ----- Automatic backup -----

    def _refresh_auto(self):
        folder = auto_backup.folder
        on = bool(folder)
        self.lbl_folder.configure(text=f"Saving to {folder}" if on else "Off. Choose a folder to turn it on.")
        if not on:
            status, colour = "", MUTED_TEXT
        elif auto_backup.last_error:
            status, colour = f"The last backup failed: {auto_backup.last_error}", ERROR_RED
        elif auto_backup.last_backup:
            status, colour = f"Last backup {_when(auto_backup.last_backup)}", MUTED_TEXT
        else:
            status, colour = "No backup saved there yet.", MUTED_TEXT
        self.lbl_status.configure(text=status, text_color=colour)
        self.btn_now.configure(state="normal" if on else "disabled")
        self.btn_off.configure(state="normal" if on else "disabled")

    def _choose_folder(self):
        clouds = bk.cloud_folders()
        start = auto_backup.folder or (clouds[0][1] if clouds else os.path.expanduser("~"))
        folder = filedialog.askdirectory(parent=self, title="Folder for automatic backups", initialdir=start)
        if folder:
            self._use_folder(folder)

    def _use_folder(self, folder: str):
        if folder:
            try:
                os.makedirs(folder, exist_ok=True)
            except OSError as e:
                messagebox.showerror("Automatic backup", f"The folder could not be made:\n{e}", parent=self)
                return
        auto_backup.folder = os.path.normpath(folder) if folder else ""
        if folder:
            self._backup_now(quiet=True)
        self._refresh_auto()

    def _backup_now(self, quiet: bool = False):
        try:
            auto_backup.backup_now(force=not quiet)
        except OSError:
            pass
        self._refresh_auto()

    # ----- Backup file -----

    def _export(self):
        name = f"Cube Labeler backup {datetime.now():%Y-%m-%d}{BACKUP_EXTENSION}"
        path = filedialog.asksaveasfilename(parent=self, title="Export backup", initialfile=name,
                                            defaultextension=BACKUP_EXTENSION,
                                            filetypes=[("Cube Labeler backups", f"*{BACKUP_EXTENSION}")])
        if not path:
            return
        try:
            backup = bk.export_backup(icon_manager, path)
        except OSError as e:
            messagebox.showerror("Export backup", f"The backup could not be saved:\n{e}", parent=self)
            return
        messagebox.showinfo(
            "Export backup",
            f"Saved {len(backup.icons)} icons, {len(backup.templates)} templates and your settings to\n{path}",
            parent=self,
        )

    def _import(self):
        path = filedialog.askopenfilename(parent=self, title="Restore backup", filetypes=FILE_TYPES)
        if not path:
            return
        try:
            with open(path, "rb") as f:
                backup = bk.read_backup(f)
        except (BackupError, OSError) as e:
            messagebox.showerror("Restore backup", str(e), parent=self)
            return
        if not backup.parts:
            messagebox.showinfo("Restore backup", "This backup is empty.", parent=self)
            return
        plan = bk.plan_import(icon_manager, backup)
        dialog = RestoreDialog(self, backup, plan)
        self.wait_window(dialog)
        self._grab()
        if dialog.choice is None:
            return
        parts, clash = dialog.choice

        try:
            result = bk.restore_backup(icon_manager, backup, clash, parts=parts)
        except OSError as e:
            messagebox.showerror("Restore backup", f"The backup could not be restored:\n{e}", parent=self)
            self._on_changed()
            return
        self._on_changed()
        done = []
        if ICONS in parts:
            line = f"Icons: added {result.added}"
            if result.replaced:
                line += f", replaced {result.replaced}"
            if result.skipped:
                line += f", skipped {result.skipped}"
            if result.unchanged:
                line += f", {result.unchanged} were already here"
            done.append(line + ".")
        if TEMPLATES in parts:
            line = f"Templates: added {result.templates_added}"
            if result.templates_replaced:
                line += f", replaced {result.templates_replaced}"
            if result.templates_skipped:
                line += f", skipped {result.templates_skipped}"
            done.append(line + ".")
        if result.settings_restored:
            done.append("Settings restored. Restart Cube Labeler to use all of them.")
        messagebox.showinfo("Restore backup", "\n".join(done), parent=self)
