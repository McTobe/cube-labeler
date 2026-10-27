#!/usr/bin/env python3
"""
Renders the app icon drawing assets/icon.svg to the files the apps use:

    assets/icon.png   1024 x 1024, for the web app (build.py makes its 192 and 512 px icons from it)
    assets/icon.ico   16 to 256 px, for the desktop window and CubeLabeler.exe

Only needed when the drawing changes. Needs resvg-py:

    pip install resvg-py
    python tools/build_app_icon.py
"""

import io
import os

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SVG = os.path.join(ROOT, "assets", "icon.svg")
ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]


def render(size: int) -> Image.Image:
    import resvg_py

    png = resvg_py.svg_to_bytes(svg_path=SVG, width=size, height=size)
    return Image.open(io.BytesIO(bytes(png))).convert("RGBA")


def main() -> None:
    render(1024).save(os.path.join(ROOT, "assets", "icon.png"))
    # Each size is drawn on its own, so the small ones stay crisp instead of being shrunk
    frames = [render(s) for s in ICO_SIZES]
    frames[-1].save(os.path.join(ROOT, "assets", "icon.ico"), sizes=[(s, s) for s in ICO_SIZES],
                    append_images=frames[:-1])
    print("Wrote assets/icon.png and assets/icon.ico")


if __name__ == "__main__":
    main()
