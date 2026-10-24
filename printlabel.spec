# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller specification for Cube Labeler (CubeLabeler.exe).
Builds a single, standalone, portable executable bundled with all assets,
themes, and dependencies.
"""

import sys
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Locate project directory and assets
project_dir = os.path.abspath(SPECPATH)
assets_dir = os.path.join(project_dir, 'assets')
icon_path = os.path.join(assets_dir, 'icon.ico')

# Collect CustomTkinter assets and submodules
ctk_datas = collect_data_files('customtkinter')
ctk_submodules = collect_submodules('customtkinter')

# Bundled data files
datas = ctk_datas + [
    (assets_dir, 'assets'),
]

# Ensure all application modules and third-party dependencies are included
hiddenimports = ctk_submodules + [
    'PIL',
    'PIL.Image',
    'PIL.ImageDraw',
    'PIL.ImageFont',
    'PIL.ImageOps',
    'serial',
    'serial.tools.list_ports',
    'serial.tools.list_ports_windows',
    'qrcode',
    'packbits',
    'darkdetect',
    'winreg',
    'ctypes',
    'ctypes.wintypes',
    'threading',
    'queue',
    'dataclasses',
    'core',
    'core.cli',
    'core.config',
    'core.icon_manager',
    'core.ai_generator',
    'core.icon_editor',
    'core.font_manager',
    'core.inventory_renderer',
    'core.label_renderer',
    'core.printer',
    'core.ptcbp',
    'core.ptstatus',
    'ui',
    'ui.app',
    'ui.inventory_tab',
    'ui.icon_browser',
    'ui.icon_editor_dialog',
    'ui.tape_preview',
    'ui.templates',
]

a = Analysis(
    ['main.py'],
    pathex=[project_dir],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter.test', 'unittest', 'test'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='CubeLabeler',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX-packed executables often trigger antivirus false positives
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_path if os.path.isfile(icon_path) else None,
)
