#!/usr/bin/env python3
"""
CLI interface for Brother PT-P300BT Label Printer.
Allows direct command-line printing, querying status, feeding tape, and listing ports.
"""

import sys
import os
import re
import argparse
from typing import List, Optional

from core.printer import BrotherPrinter, MockBrotherPrinter, list_serial_ports
from core.label_renderer import LabelRenderer, LabelConfig
from core.ptstatus import PrinterStatus


def print_ports() -> int:
    """Lists available serial COM ports and highlights Brother printers."""
    ports = list_serial_ports()
    if not ports:
        print("No serial COM ports detected.")
        return 0

    print("Available Serial Ports:")
    for opt in ports:
        tag = ""
        if opt.is_brother and opt.is_preferred:
            tag = " [Brother PT-P300BT - Preferred]"
        elif opt.is_brother:
            tag = " [Brother Printer]"
        elif opt.is_incoming:
            tag = " [BT Incoming]"
        print(f"  {opt.device:6} - {opt.label}{tag}")
    return 0


def query_status(port: str, virtual: bool = False) -> int:
    """Connects to printer and prints telemetry status."""
    print(f"Connecting to {'Virtual Mock' if virtual else port}...")
    try:
        printer = MockBrotherPrinter() if virtual else BrotherPrinter(port)
        status = printer.get_status()
        print("\n--- Printer Telemetry ---")
        print(f"Model: {status.model_name or 'PT-P300BT'}")
        print(f"Tape Width: {status.tape_width_mm}mm ({status.tape_type_name})")
        print(f"Tape Color: {status.bg_color_name} (Text: {status.fg_color_name})")
        print(f"Power: {status.power_status}")
        print(f"Status: {status.status_type_name}")
        if status.errors:
            print(f"ERRORS: {', '.join(status.errors)}")
        else:
            print("Errors: None (Ready)")
        return 0
    except Exception as e:
        print(f"Error querying status: {e}", file=sys.stderr)
        return 1


def feed_tape(port: str, mm: float = 25.0, virtual: bool = False) -> int:
    """Feeds tape by specified millimeters."""
    print(f"Feeding {mm}mm tape on {'Virtual Mock' if virtual else port}...")
    try:
        printer = MockBrotherPrinter() if virtual else BrotherPrinter(port)
        status = printer.feed_tape(length_mm=mm)
        if status.completion_confirmed:
            print("Tape fed successfully (confirmed by printer).")
        else:
            print("Feed sent, but the printer did not confirm completion.")
        return 0
    except Exception as e:
        print(f"Error feeding tape: {e}", file=sys.stderr)
        return 1


def print_label(
    port: str,
    text: str,
    font_name: str = "Arial",
    font_size: Optional[int] = None,
    image_path: Optional[str] = None,
    no_feed: bool = False,
    auto_cut: bool = False,
    cut_guide: bool = True,
    end_margin_dots: int = 0,
    preview_only: bool = False,
    save_png: Optional[str] = None,
    virtual: bool = False,
    width_mm: Optional[float] = None,
) -> int:
    """Renders and prints a label."""
    cfg = LabelConfig(
        text=text,
        fixed_width_mm=width_mm,
        font_name=font_name,
        auto_fit_font=(font_size is None),
        fixed_font_size=font_size or 40,
        image_path=image_path if image_path and os.path.isfile(image_path) else None,
        cut_line=cut_guide,
        auto_cut_hardware=auto_cut,
        end_margin=end_margin_dots,
    )

    renderer = LabelRenderer()
    print(f"Rendering label: '{text.replace(chr(10), ' / ')}'...")
    try:
        preview_img, raster_img, raster_bytes, metrics = renderer.render(cfg)
    except Exception as e:
        print(f"Render error: {e}", file=sys.stderr)
        return 1

    print(f"Label metrics: {metrics.print_length_mm:.1f}mm length, {metrics.total_used_length_mm:.1f}mm tape used.")
    if metrics.warning:
        print(f"Warning: {metrics.warning}", file=sys.stderr)

    if save_png:
        try:
            preview_img.save(save_png)
            print(f"Saved preview image to {save_png}")
        except Exception as e:
            print(f"Error saving PNG: {e}", file=sys.stderr)

    if preview_only:
        print("Preview-only mode; skipping print.")
        return 0

    if metrics.total_used_length_mm > LabelRenderer.MAX_TOTAL_LENGTH_MM:
        print("Error: Label is longer than the printer allows; not printing.", file=sys.stderr)
        return 1

    print(f"Sending print job to {'Virtual Mock' if virtual else port}...")
    try:
        printer = MockBrotherPrinter() if virtual else BrotherPrinter(port)
        status = printer.print_raster_data(
            raster_data=raster_bytes,
            no_feed=no_feed,
            auto_cut=auto_cut,
            end_margin=end_margin_dots,
        )
        if status.completion_confirmed:
            print("Print completed successfully (confirmed by printer).")
        else:
            print("Print sent, but the printer did not confirm completion. Check the label.")
        return 0
    except Exception as e:
        print(f"Print error: {e}", file=sys.stderr)
        return 1


def _looks_like_port(value: str) -> bool:
    """True for values such as COM4, /dev/rfcomm0 or a pyserial URL like loop://."""
    return bool(re.match(r"^(COM\d+|/dev/\S+|\w+://.*)$", value.strip(), re.IGNORECASE))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="PrintLabel",
        description="Brother PT-P300BT Bluetooth Label Printer CLI & Utility",
        add_help=True,
    )

    parser.add_argument(
        "comport",
        nargs="?",
        help="Printer COM port (e.g. COM3 or COM7). Optional if using --ports.",
    )
    parser.add_argument(
        "text",
        nargs="*",
        help="Text to print (UTF-8). Use \\n for multi-line labels.",
    )
    parser.add_argument(
        "--font", "-f",
        default="Arial",
        help="Font family or .ttf/.otf file path (default: Arial).",
    )
    parser.add_argument(
        "--width",
        type=float,
        default=None,
        metavar="MM",
        help="Minimum label length in millimetres (pads short labels to this length).",
    )
    parser.add_argument(
        "--font-size",
        type=int,
        default=None,
        help="Manual font size (pt). If omitted, automatically fits to tape height.",
    )
    parser.add_argument(
        "--port", "-p",
        default=None,
        help="Printer COM port. Use this instead of the positional COMPORT, e.g. with --virtual.",
    )
    parser.add_argument(
        "--image", "-i",
        help="Path to image (PNG/JPG) to include on the label.",
    )
    parser.add_argument(
        "--ports", "-l",
        action="store_true",
        help="List available serial COM ports and detect Brother printers.",
    )
    parser.add_argument(
        "--status", "-s",
        action="store_true",
        help="Query and display printer telemetry (tape width, color, battery, errors).",
    )
    parser.add_argument(
        "--feed",
        type=float,
        nargs="?",
        const=25.0,
        default=None,
        metavar="MM",
        help="Feed tape by MM millimeters (default: 25mm).",
    )
    parser.add_argument(
        "--no-feed", "-F",
        action="store_true",
        help="Disable feeding at end of print (for continuous chaining).",
    )
    parser.add_argument(
        "--auto-cut",
        action="store_true",
        help="Send the printer's auto-cut flag (the PT-P300BT prints a ':' cut mark for it).",
    )
    parser.add_argument(
        "--no-cut",
        action="store_true",
        help=argparse.SUPPRESS,  # Old flag; auto-cut is now off unless --auto-cut is given
    )
    parser.add_argument(
        "--no-cut-guide",
        action="store_true",
        help="Leave out the cut mark at the start of the label.",
    )
    parser.add_argument(
        "--cut-guide",
        action="store_true",
        help=argparse.SUPPRESS,  # Old flag; cut lines are now on by default
    )
    parser.add_argument(
        "--save-png",
        help="Save label preview rendering to specified PNG file path.",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Render and display metrics without sending to physical printer.",
    )
    parser.add_argument(
        "--virtual", "-v",
        action="store_true",
        help="Run in virtual mock mode without physical hardware.",
    )
    parser.add_argument(
        "--gui", "-g",
        action="store_true",
        help="Launch the desktop graphical user interface.",
    )

    return parser


def cli_main(args: Optional[List[str]] = None) -> int:
    parser = build_parser()
    parsed = parser.parse_args(args)

    if parsed.ports:
        return print_ports()

    if parsed.gui:
        from ui.app import main as gui_main
        gui_main()
        return 0

    # The first positional is only a port if it looks like one; otherwise it is label text.
    # This makes "PrintLabel -v Hello" and "PrintLabel --port COM4 Hello" work as expected.
    if parsed.comport and (parsed.port or not _looks_like_port(parsed.comport)):
        parsed.text = [parsed.comport] + list(parsed.text)
        parsed.comport = None
    if parsed.port:
        parsed.comport = parsed.port

    if not parsed.comport and not parsed.virtual:
        # Check if text was passed as first arg or if no args given
        if not parsed.text and not parsed.status and parsed.feed is None:
            parser.print_help()
            return 0
        print("Error: COM port required (e.g. PrintLabel COM3 'Text')", file=sys.stderr)
        return 1

    port = parsed.comport or "COM_MOCK"

    if parsed.status:
        return query_status(port, virtual=parsed.virtual)

    if parsed.feed is not None:
        return feed_tape(port, mm=parsed.feed, virtual=parsed.virtual)

    # Print label mode
    if not parsed.text and not parsed.image:
        print("Error: Specify text to print or an --image path.", file=sys.stderr)
        return 1

    text_to_print = " ".join(parsed.text) if parsed.text else ""
    return print_label(
        port=port,
        text=text_to_print,
        font_name=parsed.font,
        font_size=parsed.font_size,
        image_path=parsed.image,
        no_feed=parsed.no_feed,
        auto_cut=parsed.auto_cut and not parsed.no_cut,
        cut_guide=not parsed.no_cut_guide,
        preview_only=parsed.preview,
        save_png=parsed.save_png,
        virtual=parsed.virtual,
        width_mm=parsed.width,
    )


if __name__ == "__main__":
    sys.exit(cli_main())
