#!/usr/bin/env python3
"""
Automated build script for Cube Labeler.
Compiles the application into a single portable executable (dist/CubeLabeler.exe).
"""

import sys
import os
import subprocess
import shutil

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))


def check_prerequisites():
    print("[1/4] Checking build prerequisites...")
    required_packages = [
        "PyInstaller",
        "customtkinter",
        "PIL",
        "serial",
        "qrcode",
        "packbits",
    ]
    missing = []
    for pkg in required_packages:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)

    if missing:
        print(f"Error: Missing required packages: {', '.join(missing)}")
        print("Install them via: pip install -r requirements.txt pyinstaller")
        sys.exit(1)
    print("  [OK] All required Python modules found.")


def ensure_icon():
    print("[2/4] Ensuring application icon exists...")
    assets_dir = os.path.join(PROJECT_ROOT, "assets")
    os.makedirs(assets_dir, exist_ok=True)
    icon_path = os.path.join(assets_dir, "icon.ico")

    if not os.path.isfile(icon_path):
        print("  Generating assets/icon.ico...")
        from PIL import Image, ImageDraw

        sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
        images = []
        for w, h in sizes:
            img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            s = w / 256.0

            # Body
            draw.rounded_rectangle([16 * s, 32 * s, 240 * s, 230 * s], radius=28 * s, fill="#1e293b", outline="#334155", width=int(max(1, 4 * s)))
            # Cyan stripe
            draw.rectangle([16 * s, 70 * s, 240 * s, 86 * s], fill="#0284c7")
            # Slot
            draw.rounded_rectangle([60 * s, 20 * s, 196 * s, 34 * s], radius=4 * s, fill="#0f172a", outline="#475569", width=int(max(1, 2 * s)))
            # Tape
            draw.rectangle([70 * s, 8 * s, 186 * s, 30 * s], fill="#ffffff", outline="#94a3b8", width=int(max(1, 2 * s)))
            # LED
            led = (50 * s, 54 * s)
            r = 8 * s
            draw.ellipse([led[0] - r, led[1] - r, led[0] + r, led[1] + r], fill="#22c55e", outline="#16a34a", width=int(max(1, 2 * s)))
            # Tag
            draw.rounded_rectangle([64 * s, 115 * s, 192 * s, 195 * s], radius=16 * s, fill="#38bdf8", outline="#e0f2fe", width=int(max(1, 3 * s)))
            images.append(img)

        images[0].save(icon_path, format="ICO", sizes=[(im.width, im.height) for im in images], append_images=images[1:])
        print("  [OK] Icon generated successfully.")
    else:
        print("  [OK] Application icon present.")


def run_pyinstaller():
    print("[3/4] Compiling portable single .exe with PyInstaller...")
    spec_path = os.path.join(PROJECT_ROOT, "printlabel.spec")

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        spec_path,
    ]

    print(f"  Executing: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    if result.returncode != 0:
        print("Error: PyInstaller compilation failed!")
        sys.exit(result.returncode)
    print("  [OK] PyInstaller compilation completed.")


def verify_output():
    print("[4/4] Verifying generated executable...")
    dist_dir = os.path.join(PROJECT_ROOT, "dist")
    exe_path = os.path.join(dist_dir, "CubeLabeler.exe")

    if not os.path.isfile(exe_path):
        print(f"Error: Expected output file not found at {exe_path}")
        sys.exit(1)

    size_bytes = os.path.getsize(exe_path)
    size_mb = size_bytes / (1024 * 1024)

    print("\n" + "=" * 60)
    print("BUILD SUCCESSFUL!")
    print(f"Standalone Executable: {exe_path}")
    print(f"File Size:             {size_mb:.2f} MB ({size_bytes:,} bytes)")
    print("Portability:           100% self-contained (Single .exe)")
    print("=" * 60)


def main():
    print("=== Cube Labeler: Build Pipeline ===")
    check_prerequisites()
    ensure_icon()
    run_pyinstaller()
    verify_output()


if __name__ == "__main__":
    main()
