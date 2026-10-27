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
        # It is rendered from assets/icon.svg and kept in the repository
        print("Error: assets/icon.ico is missing. Make it with: python tools/build_app_icon.py")
        sys.exit(1)
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
