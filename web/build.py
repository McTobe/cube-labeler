#!/usr/bin/env python3
"""
Builds the Cube Labeler web app into web/dist/, a static folder any web server can host.

    python web/build.py
    python -m http.server 8000 -d web/dist     # then open http://localhost:8000/

The page needs a secure context for Web Serial: localhost works, anything else needs HTTPS.
"""

import hashlib
import json
import os
import shutil
import sys
import zipfile

WEB_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(WEB_DIR)
DIST_DIR = os.path.join(WEB_DIR, "dist")

PAGE_FILES = ["index.html", "printer.js", "style.css"]
PAGE_DIRS = ["js", "vendor"]

# The parts of core/ the web app runs; the rest needs the desktop (tkinter, pyserial, registry)
CORE_MODULES = [
    "__init__.py",
    "font_manager.py",
    "inventory_renderer.py",
    "label_language.py",
    "label_renderer.py",
    "protocol.py",
    "ptcbp.py",
    "ptstatus.py",
    "rich_text.py",
    "specs.py",
]

FONTS = ["Arimo-Regular.ttf", "Arimo-Bold.ttf", "OFL.txt"]

MANIFEST = {
    "name": "Cube Labeler",
    "short_name": "Cube Labeler",
    "description": "Design and print labels on the Brother PT-P300BT.",
    "start_url": ".",
    "display": "standalone",
    "background_color": "#1f2430",
    "theme_color": "#1f2430",
    "icons": [
        {"src": "icon-192.png", "sizes": "192x192", "type": "image/png"},
        {"src": "icon-512.png", "sizes": "512x512", "type": "image/png"},
    ],
}


def build_core_zip(path: str) -> None:
    """Packs the Python side: core modules, cube_web.py and the fonts (in ~/.fonts in Pyodide)."""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in CORE_MODULES:
            zf.write(os.path.join(PROJECT_ROOT, "core", name), f"core/{name}")
        zf.write(os.path.join(WEB_DIR, "cube_web.py"), "cube_web.py")
        for name in FONTS:
            zf.write(os.path.join(WEB_DIR, "fonts", name), f".fonts/{name}")
        # The icon library: bin labels draw their drive and part icons from it
        icons_dir = os.path.join(PROJECT_ROOT, "assets", "icons")
        for root, _, names in os.walk(icons_dir):
            for name in sorted(names):
                path = os.path.join(root, name)
                zf.write(path, "assets/icons/" + os.path.relpath(path, icons_dir).replace(os.sep, "/"))


def build_icons() -> None:
    from PIL import Image

    with Image.open(os.path.join(PROJECT_ROOT, "assets", "icon.ico")) as ico:
        ico.size = max(ico.ico.sizes())
        icon = ico.convert("RGBA")
    for size in (192, 512):
        icon.resize((size, size), Image.Resampling.LANCZOS).save(
            os.path.join(DIST_DIR, f"icon-{size}.png")
        )


def build_service_worker() -> None:
    """Writes sw.js with the list of the app's files and a build id that changes with them."""
    files, digest = [], hashlib.sha256()
    for root, _, names in sorted(os.walk(DIST_DIR)):
        for name in sorted(names):
            path = os.path.join(root, name)
            rel = os.path.relpath(path, DIST_DIR).replace(os.sep, "/")
            files.append(rel)
            digest.update(rel.encode())
            with open(path, "rb") as f:
                digest.update(f.read())
    files = ["./"] + [f for f in files if f != "index.html"] + ["index.html"]
    with open(os.path.join(WEB_DIR, "sw.js"), encoding="utf-8") as f:
        source = f.read()
    source = source.replace("'__BUILD__'", json.dumps(digest.hexdigest()[:12]))
    source = source.replace("__APP_FILES__", json.dumps(files))
    with open(os.path.join(DIST_DIR, "sw.js"), "w", encoding="utf-8") as f:
        f.write(source)


def empty_dist() -> None:
    """
    Removes the files of the last build but keeps its folders: a server running from dist/
    keeps working, and Windows often refuses to delete a folder that Explorer, the search
    indexer or a virus scanner is looking at. Folders left empty are tidied up if possible.
    """
    os.makedirs(DIST_DIR, exist_ok=True)
    for root, dirs, files in os.walk(DIST_DIR, topdown=False):
        for name in files:
            os.remove(os.path.join(root, name))
        for name in dirs:
            try:
                os.rmdir(os.path.join(root, name))
            except OSError:
                pass  # in use; the build fills it again or leaves it empty


def main() -> int:
    empty_dist()
    for name in PAGE_FILES:
        shutil.copy2(os.path.join(WEB_DIR, name), DIST_DIR)
    for name in PAGE_DIRS:
        shutil.copytree(os.path.join(WEB_DIR, name), os.path.join(DIST_DIR, name), dirs_exist_ok=True)
    build_core_zip(os.path.join(DIST_DIR, "cube_core.zip"))
    build_icons()
    with open(os.path.join(DIST_DIR, "manifest.webmanifest"), "w", encoding="utf-8") as f:
        json.dump(MANIFEST, f, indent=2)
    build_service_worker()

    print(f"Built {DIST_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
