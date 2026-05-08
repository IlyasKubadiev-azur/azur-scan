# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for azur-scan-agent-setup.exe

Windowed (no console), UAC elevation via manifest (uac_admin=True).
Bundles: installer_main.py + azurscan-agent.exe + WinSW + config XML.
"""
from pathlib import Path

SPEC_DIR  = Path(SPECPATH).resolve()
AGENT_DIR = SPEC_DIR.parent.parent
DIST_DIR  = AGENT_DIR / "dist"
ENTRY     = str(SPEC_DIR / "installer_main.py")

a = Analysis(
    [ENTRY],
    pathex=[],
    binaries=[],
    datas=[
        (str(DIST_DIR / "azurscan-agent.exe"),   "."),
        (str(SPEC_DIR / "azurscan-service.exe"), "."),
        (str(SPEC_DIR / "azurscan-service.xml"), "."),
    ],
    hiddenimports=[
        "tkinter",
        "tkinter.ttk",
        "tkinter.messagebox",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=["matplotlib", "numpy", "pandas", "PIL"],
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="azur-scan-agent-setup",
    debug=False,
    strip=False,
    upx=False,
    console=False,      # no black console window
    uac_admin=True,     # manifest: request elevation on launch
    target_arch=None,
)
