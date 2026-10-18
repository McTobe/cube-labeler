#!/usr/bin/env python3
"""
Printer status chip for the header, and the small panel it opens with the
connection controls (port, scan, status check, simulation).
"""

from typing import Callable, List, Optional

import customtkinter as ctk

from ui.widgets import MUTED_TEXT

# State -> (text colour, background) for the chip
CHIP_STYLES = {
    "ready": ("#E8F5E9", "#2E7D32"),
    "problem": ("#FFEBEE", "#C62828"),
    "connecting": ("#3E2723", "#F9A825"),
    "offline": ("gray90", "gray35"),
    "simulation": ("#E3F2FD", "#1565C0"),
}


class PrinterChip(ctk.CTkButton):
    """A pill showing the printer state, e.g. "PT-P300BT · 12mm white · battery full"."""

    def __init__(self, master, command: Callable[[], None], **kwargs):
        super().__init__(
            master,
            text="Printer: not connected",
            height=30,
            corner_radius=15,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=command,
            **kwargs,
        )
        self.state_name = "offline"
        self.set_state("offline", "Printer: not connected")

    def set_state(self, state: str, text: str):
        self.state_name = state
        fg_text, bg = CHIP_STYLES.get(state, CHIP_STYLES["offline"])
        self.configure(text=f"●  {text}  ▾", fg_color=bg, hover_color=bg, text_color=fg_text)


class PrinterPanel(ctk.CTkFrame):
    """Connection controls shown under the chip. Placed over the window, toggled by the chip."""

    def __init__(
        self,
        master,
        port_var: ctk.StringVar,
        virtual_var: ctk.BooleanVar,
        on_port_selected: Callable[[str], None],
        on_scan: Callable[[], None],
        on_check: Callable[[], None],
        on_virtual_toggle: Callable[[], None],
        **kwargs,
    ):
        super().__init__(master, corner_radius=10, border_width=1, border_color=("gray70", "gray30"), **kwargs)

        ctk.CTkLabel(self, text="Printer", font=ctk.CTkFont(size=14, weight="bold"), anchor="w").pack(
            fill="x", padx=14, pady=(12, 4)
        )
        self.detail_label = ctk.CTkLabel(
            self, text="Not connected", anchor="w", justify="left", text_color=MUTED_TEXT, wraplength=300
        )
        self.detail_label.pack(fill="x", padx=14, pady=(0, 8))

        ctk.CTkLabel(self, text="Port", anchor="w").pack(fill="x", padx=14)
        self.port_combo = ctk.CTkComboBox(
            self, variable=port_var, values=["Scanning..."], width=300, command=on_port_selected
        )
        self.port_combo.pack(fill="x", padx=14, pady=(2, 8))

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.pack(fill="x", padx=14, pady=(0, 8))
        self.btn_refresh_ports = ctk.CTkButton(buttons, text="Scan ports", width=100, command=on_scan)
        self.btn_refresh_ports.pack(side="left")
        self.btn_query_status = ctk.CTkButton(buttons, text="Check status", width=110, command=on_check)
        self.btn_query_status.pack(side="left", padx=8)

        self.virtual_switch = ctk.CTkSwitch(
            self,
            text="Simulation (no printer needed)",
            variable=virtual_var,
            command=on_virtual_toggle,
        )
        self.virtual_switch.pack(anchor="w", padx=14, pady=(4, 14))

    def set_details(self, lines: List[str]):
        self.detail_label.configure(text="\n".join(lines) if lines else "Not connected")
