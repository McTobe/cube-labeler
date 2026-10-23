#!/usr/bin/env python3
"""
Renders the icon library drawings in icons-src/<category>/<id>.svg to the PNGs the app
uses in assets/icons/<category>/<id>.png, and can write a review sheet that shows every
icon next to how it prints on 12 mm tape.

Only needed when a drawing changes; the app itself reads the PNGs. Needs resvg-py:

    pip install resvg-py
    python tools/build_icons.py                       # render every drawing
    python tools/build_icons.py --sheet review.png    # also write a review sheet
    python tools/build_icons.py --sheet review.png tools safety   # only these categories

Drawings use a 64 x 64 viewBox: one unit is one printed dot on 12 mm tape. Black is ink,
white cuts details out of a black shape, and anything else is left transparent.
"""

import argparse
import io
import json
import os
import sys

from PIL import Image, ImageDraw, ImageFont

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(PROJECT_ROOT, "icons-src")
ICONS_DIR = os.path.join(PROJECT_ROOT, "assets", "icons")
SIZE = 256
PRINT_DOTS = 56       # icon height on a 12 mm bin label
PRINT_THRESHOLD = 100  # same cut-off as the label renderer


def render_svg(svg_path: str) -> Image.Image:
    """Renders a drawing to a 3-colour RGBA picture: transparent, black and white."""
    import resvg_py

    png = resvg_py.svg_to_bytes(svg_path=svg_path, width=SIZE, height=SIZE)
    img = Image.open(io.BytesIO(bytes(png))).convert("RGBA")
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    src, dst = img.load(), out.load()
    for y in range(img.height):
        for x in range(img.width):
            r, g, b, a = src[x, y]
            if a >= 128:
                dst[x, y] = (255, 255, 255, 255) if (r + g + b) / 3 >= 128 else (0, 0, 0, 255)
    return out


def print_preview(img: Image.Image) -> Image.Image:
    """How the icon comes out on tape: shrunk to PRINT_DOTS and cut to black and white."""
    flat = Image.new("RGBA", img.size, "white")
    flat.alpha_composite(img)
    gray = flat.convert("L")
    bbox = gray.point(lambda v: 255 if v < 240 else 0).getbbox()
    if bbox:
        gray = gray.crop(bbox)
    gray.thumbnail((PRINT_DOTS, PRINT_DOTS), Image.Resampling.LANCZOS)
    return gray.point(lambda v: 255 if v > PRINT_THRESHOLD else 0)


def load_catalog() -> dict:
    with open(os.path.join(ICONS_DIR, "catalog.json"), encoding="utf-8") as f:
        return json.load(f)


def build(categories) -> list:
    """Renders the drawings; returns (category, id, png path) for every rendered icon."""
    catalog = load_catalog()
    known_folders = [c["folder"] for c in catalog["categories"]]
    built = []
    for folder in sorted(os.listdir(SRC_DIR)):
        src_folder = os.path.join(SRC_DIR, folder)
        if not os.path.isdir(src_folder) or (categories and folder not in categories):
            continue
        if folder not in known_folders:
            sys.exit(f"icons-src/{folder} is not a category in assets/icons/catalog.json")
        for name in sorted(os.listdir(src_folder)):
            if not name.endswith(".svg"):
                continue
            icon_id = name[:-4]
            if icon_id not in catalog["icons"]:
                sys.exit(f"{folder}/{name} has no entry in assets/icons/catalog.json")
            png_path = os.path.join(ICONS_DIR, folder, icon_id + ".png")
            os.makedirs(os.path.dirname(png_path), exist_ok=True)
            render_svg(os.path.join(src_folder, name)).save(png_path, optimize=True)
            built.append((folder, icon_id, png_path))
            print(f"rendered {folder}/{icon_id}.png")
    return built


def write_sheet(path: str, categories) -> None:
    """One tile per icon: the picture, then how it prints (shown at 2x), then its title."""
    catalog = load_catalog()
    try:
        font = ImageFont.truetype(os.path.join(PROJECT_ROOT, "tests", "fonts", "Roboto-Regular.ttf"), 14)
        head = ImageFont.truetype(os.path.join(PROJECT_ROOT, "tests", "fonts", "Roboto-Regular.ttf"), 22)
    except OSError:
        font = head = ImageFont.load_default()

    groups = []
    for cat in catalog["categories"]:
        if categories and cat["folder"] not in categories:
            continue
        folder = os.path.join(ICONS_DIR, cat["folder"])
        names = sorted(n for n in os.listdir(folder) if n.endswith(".png")) if os.path.isdir(folder) else []
        if names:
            groups.append((cat, names))

    cols, tile_w, tile_h = 6, 300, 190
    height = 10 + sum(40 + -(-len(names) // cols) * tile_h for _, names in groups)
    sheet = Image.new("RGB", (cols * tile_w + 20, height), "white")
    draw = ImageDraw.Draw(sheet)
    y = 10
    for cat, names in groups:
        draw.text((10, y), cat["name"], fill="black", font=head)
        y += 40
        for i, name in enumerate(names):
            x, ty = 10 + (i % cols) * tile_w, y + (i // cols) * tile_h
            img = Image.open(os.path.join(ICONS_DIR, cat["folder"], name)).convert("RGBA")
            flat = Image.new("RGBA", img.size, "white")
            flat.alpha_composite(img)
            sheet.paste(flat.convert("RGB").resize((140, 140), Image.Resampling.LANCZOS), (x + 5, ty + 5))
            dots = print_preview(img)
            dots = dots.resize((dots.width * 2, dots.height * 2), Image.Resampling.NEAREST)
            sheet.paste(dots, (x + 155 + (130 - dots.width) // 2, ty + 5 + (140 - dots.height) // 2))
            draw.rectangle([x + 150, ty + 2, x + 290, ty + 148], outline=(200, 200, 200))
            title = catalog["icons"].get(name[:-4], {}).get("title", name[:-4])
            draw.text((x + 5, ty + 155), title, fill="black", font=font)
        y += -(-len(names) // cols) * tile_h
    sheet.save(path)
    print(f"review sheet: {path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("categories", nargs="*", help="category folders to render (default: all)")
    parser.add_argument("--sheet", help="also write a review sheet PNG to this path")
    parser.add_argument("--sheet-only", action="store_true", help="write the sheet without rendering")
    args = parser.parse_args()
    if not args.sheet_only:
        build(args.categories)
    if args.sheet:
        write_sheet(args.sheet, args.categories)


if __name__ == "__main__":
    main()
