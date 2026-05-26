# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


project_root = Path(SPECPATH).resolve().parents[1]

datas = [
    (str(project_root / "web" / "templates"), "web/templates"),
    (str(project_root / "web" / "static"), "web/static"),
    (str(project_root / "Readme.md"), "."),
]


a = Analysis(
    [str(project_root / "desktop_launcher.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="CustomerAgent",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="CustomerAgent",
)
