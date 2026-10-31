#!/usr/bin/env python3
"""
Hardware test for "stop at each cut": prints four small labels (A to D, 15 mm each) as short
chained print jobs. Each job stops when the next cut line should sit at the cutter, so you
can check where it lands, cut, and carry on. The last step feeds the strip out.

Around every cut line there are 1 mm ticks (five on each side), so after cutting you can count
how far the cut landed from the dotted line. About 8 cm of tape in all.

    python tools/cut_test.py [COM port] [--head-mm 22.5] [--start-feed-mm 2.5]

First run (2026-10-31, head 25 mm, no start feed) cut 2.6, 5.0 and 5.3 mm past the lines: the
cutter is about 22.4 mm from the head, and each chained job feeds about 2.5 mm before printing.
"""

import argparse
import os
import sys

from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import protocol  # noqa: E402
from core.printer import BrotherPrinter, MockBrotherPrinter, list_serial_ports  # noqa: E402
from core.specs import DOT_PITCH_MM, PRINTHEAD_DOTS, TAPE_SPECS, tape_width_from_status  # noqa: E402

LABEL_MM = 15.0
LETTERS = "ABCD"
EDGE_DOTS = 14  # blank tape before the first and after the last label, like a queue strip
FONT = os.path.join(ROOT, "web", "fonts", "Arimo-Bold.ttf")


def dots(mm: float) -> int:
    return int(round(mm / DOT_PITCH_MM))


def test_strip(tape_width_mm: float):
    """The strip as a 128-dot raster, and the raster line of each cut line between labels."""
    printable = TAPE_SPECS[tape_width_mm]["printable_height"]
    top = (PRINTHEAD_DOTS - printable) // 2
    label = dots(LABEL_MM)
    length = 2 * EDGE_DOTS + label * len(LETTERS)
    img = Image.new("L", (length, PRINTHEAD_DOTS), 255)
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONT, int(printable * 0.55))
    tick = max(4, printable // 8)

    def cut_line(x: int):
        for y in range(top, top + printable, 4):
            draw.line([(x, y), (x, y + 1)], fill=0)
        # 1 mm ticks on both sides, every fifth one longer
        for mm in range(-5, 6):
            if mm == 0:
                continue
            tx = x + int(round(mm / DOT_PITCH_MM))
            h = tick * 2 if abs(mm) == 5 else tick
            draw.line([(tx, top), (tx, top + h)], fill=0)
            draw.line([(tx, top + printable - 1 - h), (tx, top + printable - 1)], fill=0)

    cuts = []
    x = EDGE_DOTS
    for n, letter in enumerate(LETTERS):
        if n:
            cut_line(x)
            cuts.append(x)
        draw.text((x + label / 2, top + printable / 2), letter, font=font, fill=0, anchor="mm")
        x += label

    # The same turn as the label renderer: along the tape becomes down the raster
    raster = ImageOps.mirror(ImageOps.invert(img).rotate(-90, expand=True)).point(lambda p: 255 if p > 128 else 0).convert("1")
    return raster.tobytes(), cuts


def pick_port(given):
    if given:
        return given
    ports = [p for p in list_serial_ports() if p.is_preferred] or [p for p in list_serial_ports() if not p.is_incoming]
    if not ports:
        sys.exit("No printer port found. Pass the COM port, e.g. python tools/cut_test.py COM5")
    return ports[0].device


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("port", nargs="?", help="COM port of the printer (found automatically if left out)")
    parser.add_argument("--head-mm", type=float, default=22.5, help="distance from print head to cutter (default 22.5)")
    parser.add_argument("--start-feed-mm", type=float, default=2.5,
                        help="tape a chained job feeds before it prints (default 2.5)")
    parser.add_argument("--virtual", action="store_true", help="use the simulated printer")
    args = parser.parse_args()

    port = "virtual" if args.virtual else pick_port(args.port)
    printer = MockBrotherPrinter() if args.virtual else BrotherPrinter(port)
    status = printer.get_status()
    width = tape_width_from_status(status.tape_width_mm)
    print(f"Printer on {port}: {width:g} mm tape loaded.")

    raster, cuts = test_strip(width)
    lines = len(raster) // protocol.LINE_BYTES
    head = dots(args.head_mm)
    feed = dots(args.start_feed_mm)
    print(f"Test strip: {lines * DOT_PITCH_MM:.0f} mm, labels A to D. Print head to cutter: {args.head_mm:g} mm, "
          f"start feed: {args.start_feed_mm:g} mm.\n")
    input("Press Enter to start (or close this window to cancel)... ")

    start = 0
    job = 0
    printed_in = {}  # cut -> the job that printed it
    for n, cut in enumerate(cuts, 1):
        job += 1
        # A cut line printed by an earlier job moves out with every later job's start feed
        later_starts = job - printed_in.get(cut, job)
        stop = max(cut + head - feed * later_starts, start + 1)
        for c in cuts:
            if start <= c < stop:
                printed_in[c] = job
        part = raster[start * protocol.LINE_BYTES : stop * protocol.LINE_BYTES]
        if stop > lines:  # the stop lies past the strip's end: blank tape up to it
            part += bytes(protocol.LINE_BYTES * (stop - lines))
        print(f"Step {n}: printing up to the cut line after {LETTERS[n - 1]}, then stopping...")
        done = printer.print_raster_data(part, no_feed=True, required_tape_width_mm=width)
        if not done.completion_confirmed:
            print("  (the printer did not confirm this step)")
        print(f"  The dotted line between {LETTERS[n - 1]} and {LETTERS[n]} should now be at the cutter.")
        input("  Press the cutter lever, take the piece, then press Enter... ")
        start = stop

    print(f"Step {len(cuts) + 1}: feeding out label {LETTERS[-1]}...")
    blank = bytes(protocol.LINE_BYTES * protocol.feed_dots(0))
    printer.print_raster_data(raster[start * protocol.LINE_BYTES :] + blank if start < lines else blank, required_tape_width_mm=width)
    print("  Cut it off as usual.\n")
    print("Done. For each cut, count the ticks between the dotted line and the cut edge, and on which side it fell.")
    input("Press Enter to close. ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
