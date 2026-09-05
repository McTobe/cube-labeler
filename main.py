#!/usr/bin/env python3
"""
Brother P-touch Cube PT-P300BT Label Studio & CLI Utility
Entrypoint script supporting both GUI and Command-Line Interface.
"""

import sys
import os

# Handle PyInstaller onefile extraction directory
if getattr(sys, "frozen", False):
    BASE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)


def _attach_windows_console():
    """Attaches stdout/stderr to caller's console when running as windowed app on Windows."""
    if sys.platform == "win32":
        try:
            import ctypes
            # ATTACH_PARENT_PROCESS = -1
            if ctypes.windll.kernel32.AttachConsole(-1):
                # Reopen standard streams
                sys.stdout = open("CONOUT$", "w", encoding="utf-8")
                sys.stderr = open("CONOUT$", "w", encoding="utf-8")
                sys.stdin = open("CONIN$", "r", encoding="utf-8")
        except Exception:
            pass


def main():
    args = sys.argv[1:]

    # Check if CLI mode should be invoked
    # If arguments are passed and it is NOT explicitly "--gui" or "-g"
    is_cli = len(args) > 0 and not (len(args) == 1 and args[0] in ("--gui", "-g"))

    if is_cli:
        _attach_windows_console()
        from core.cli import cli_main
        sys.exit(cli_main(args))
    else:
        from ui.app import main as gui_main
        gui_main()


if __name__ == "__main__":
    main()
