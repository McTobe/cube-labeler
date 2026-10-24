#!/usr/bin/env python3
"""
Backups window for the user's icons: export and import a backup file, and automatic
backups to a folder that a cloud sync app (Google Drive, OneDrive, Dropbox) uploads.
"""

import os
from datetime import datetime
from tkinter import filedialog, messagebox
from typing import Callable, Optional

import customtkinter as ctk

from core import icon_backup
from core.icon_backup import BACKUP_EXTENSION, KEEP_BOTH, REPLACE, SKIP, BackupError, auto_backup
from core.icon_manager import icon_manager
from ui.widgets import MUTED_TEXT

ERROR_RED = "#DC2626"
BACKUP_SUBFOLDER = "Cube Labeler backups"
FILE_TYPES = [("Cube Labeler icon backups", f"*{BACKUP_EXTENSION}"), ("All files", "*.*")]


def _when(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return iso or "an unknown time"


class ClashDialog(ctk.CTkToplevel):
    """Asks what to do with backed-up icons whose names are already taken."""

    def __init__(self, parent, count: int, names: str):
        super().__init__(parent)
        self.choice: Optional[str] = None
        self.title("Icons with the same name")
        self.resizable(False, False)
        self.transient(parent)

        what = "1 icon in the backup has" if count == 1 else f"{count} icons in the backup have"
        ctk.CTkLabel(
            self, text=f"{what} the same name as one of your icons, with a different picture:\n{names}",
            justify="left", anchor="w", wraplength=420,
        ).pack(fill="x", padx=16, pady=(16, 10))
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(0, 16))
        for text, choice in (("Keep both", KEEP_BOTH), ("Replace mine", REPLACE), ("Skip them", SKIP)):
            ctk.CTkButton(row, text=text, width=110, command=lambda c=choice: self._pick(c)).pack(side="left", padx=(0, 8))
        ctk.CTkButton(row, text="Cancel", width=80, fg_color="gray30", hover_color="gray40",
                      command=self.destroy).pack(side="right")
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.after(50, self._grab)

    def _grab(self):
        try:
            self.grab_set()
            self.focus_force()
        except Exception:
            pass

    def _pick(self, choice: str):
        self.choice = choice
        self.destroy()


class BackupDialog(ctk.CTkToplevel):
    def __init__(self, parent, on_changed: Callable[[], None]):
        super().__init__(parent)
        self._on_changed = on_changed
        self.title("Icon backups")
        self.geometry("560x510")
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
        ctk.CTkLabel(self, text="Icon backups", font=ctk.CTkFont(size=18, weight="bold"), anchor="w").pack(
            fill="x", padx=16, pady=(14, 10))
        count = len(icon_manager.user_icons())
        files = self._card(
            "Backup file",
            f"One file with all your icons ({count}), with their names, categories, search words, "
            "favourites and original pictures, so they can still be edited after a restore.",
        )
        row = ctk.CTkFrame(files, fg_color="transparent")
        row.pack(fill="x")
        ctk.CTkButton(row, text="Export backup…", width=140, command=self._export).pack(side="left")
        ctk.CTkButton(row, text="Import backup…", width=140, command=self._import).pack(side="left", padx=8)

        auto = self._card(
            "Automatic backup",
            "Pick a folder that your cloud app syncs, like Google Drive, OneDrive or Dropbox. "
            f"A backup is saved there a few seconds after your icons change, and the newest {auto_backup.keep} are kept.",
        )
        self.lbl_folder = ctk.CTkLabel(auto, text="", anchor="w", justify="left", wraplength=500)
        self.lbl_folder.pack(fill="x")
        self.lbl_status = ctk.CTkLabel(auto, text="", anchor="w", justify="left", wraplength=500,
                                       font=ctk.CTkFont(size=11))
        self.lbl_status.pack(fill="x", pady=(0, 6))
        clouds = icon_backup.cloud_folders()[:3]
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
        clouds = icon_backup.cloud_folders()
        start = auto_backup.folder or (clouds[0][1] if clouds else os.path.expanduser("~"))
        folder = filedialog.askdirectory(parent=self, title="Folder for automatic icon backups", initialdir=start)
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
            path = auto_backup.backup_now(force=not quiet)
        except OSError:
            path = None
        self._refresh_auto()
        if not quiet and path is None and not auto_backup.last_error:
            messagebox.showinfo("Automatic backup", "You have no icons of your own to back up yet.", parent=self)

    # ----- Backup file -----

    def _export(self):
        if not icon_manager.user_icons():
            messagebox.showinfo("Export backup", "You have no icons of your own to back up yet.", parent=self)
            return
        name = f"Cube Labeler icons {datetime.now():%Y-%m-%d}{BACKUP_EXTENSION}"
        path = filedialog.asksaveasfilename(parent=self, title="Export icon backup", initialfile=name,
                                            defaultextension=BACKUP_EXTENSION, filetypes=FILE_TYPES)
        if not path:
            return
        try:
            count = icon_backup.export_backup(icon_manager, path)
        except OSError as e:
            messagebox.showerror("Export backup", f"The backup could not be saved:\n{e}", parent=self)
            return
        messagebox.showinfo("Export backup", f"Saved {count} icons to\n{path}", parent=self)

    def _import(self):
        path = filedialog.askopenfilename(parent=self, title="Import icon backup", filetypes=FILE_TYPES)
        if not path:
            return
        try:
            with open(path, "rb") as f:
                backup = icon_backup.read_backup(f)
        except (BackupError, OSError) as e:
            messagebox.showerror("Import backup", str(e), parent=self)
            return
        plan = icon_backup.plan_import(icon_manager, backup)
        if not plan.new and not plan.conflicts:
            messagebox.showinfo("Import backup", "You already have every icon in this backup.", parent=self)
            return

        choice = SKIP
        if plan.conflicts:
            names = ", ".join(e.title for e in plan.conflicts[:6]) + (" …" if len(plan.conflicts) > 6 else "")
            dialog = ClashDialog(self, len(plan.conflicts), names)
            self.wait_window(dialog)
            self._grab()
            if dialog.choice is None:
                return
            choice = dialog.choice
        elif not messagebox.askyesno(
            "Import backup",
            f"Add {len(plan.new)} icons from the backup made {_when(backup.created)}?",
            parent=self,
        ):
            return

        try:
            result = icon_backup.restore_backup(icon_manager, backup, choice)
        except OSError as e:
            messagebox.showerror("Import backup", f"The icons could not be restored:\n{e}", parent=self)
            self._on_changed()
            return
        self._on_changed()
        done = [f"Added {result.added}"]
        if result.replaced:
            done.append(f"replaced {result.replaced}")
        if result.skipped:
            done.append(f"skipped {result.skipped}")
        if result.unchanged:
            done.append(f"{result.unchanged} were already there")
        messagebox.showinfo("Import backup", ", ".join(done) + ".", parent=self)
