# -*- mode: python ; coding: utf-8 -*-

import sys
import os

block_cipher = None

base_dir = os.path.abspath(os.path.join(SPECPATH, ".."))
src_dir = os.path.join(SPECPATH, "src")
bin_adb_dir = os.path.join(SPECPATH, "bin", "adb")
driver_dir = os.path.join(base_dir, "driver")

added_datas = [
    (bin_adb_dir, os.path.join("bin", "adb")),
    (driver_dir, "driver"),
]

# Incluir custom tkinter assets
import customtkinter
ctk_dir = os.path.dirname(customtkinter.__file__)
added_datas.append((ctk_dir, "customtkinter"))

a = Analysis(
    [os.path.join(SPECPATH, "main.py")],
    pathex=[SPECPATH, src_dir],
    binaries=[],
    datas=added_datas,
    hiddenimports=[
        'PIL',
        'PIL._imagingtk',
        'PIL.ImageTk',
        'customtkinter',
        'pyvirtualcam',
        'cv2'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['pytest', 'unittest', 'usb'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='DroidLens',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='DroidLens',
)
