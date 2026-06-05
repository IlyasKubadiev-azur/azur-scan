# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Azur-Scan agent.

Produces a single-file binary:
  Windows: dist/azurscan-agent.exe
  macOS:   dist/azurscan-agent

Build via:
  python build/build.py

CRITICAL: PyInstaller's static analyzer misses dynamic imports inside many
3rd-party packages (click, pydantic, httpx). We use `collect_submodules` to
exhaustively pull every submodule into the bundle. Without this, the frozen
binary fails at runtime with `ModuleNotFoundError: No module named 'click'`
or similar.
"""
import sys
from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
)

block_cipher = None

SPEC_DIR = Path(SPECPATH).resolve()
AGENT_DIR = SPEC_DIR.parent
ENTRY = str(AGENT_DIR / "azurscan_agent" / "__main__.py")


def _safe(fn, name):
    try:
        return fn(name)
    except Exception as exc:  # pragma: no cover
        print(f"warning: {fn.__name__}({name!r}) failed: {exc}")
        return []


# ---------------------------------------------------------------------------
# hiddenimports
# ---------------------------------------------------------------------------

hiddenimports = [
    # our own package — listed explicitly so PyInstaller doesn't drop them
    "azurscan_agent",
    "azurscan_agent.__main__",
    "azurscan_agent.cli",
    "azurscan_agent.runtime",
    "azurscan_agent.transport",
    "azurscan_agent.collectors",
    "azurscan_agent.machine",
    "azurscan_agent.config",
    "azurscan_agent.secrets_store",
    "azurscan_agent.logging_setup",
]

# Pull every submodule of runtime deps. PyInstaller's analyzer misses many.
for pkg in (
    "click",
    "httpx",
    "httpcore",
    "h11",
    "anyio",
    "sniffio",
    "certifi",
    "idna",
    "pydantic",
    "pydantic_core",
    "pydantic_settings",
    "psutil",
    "yaml",
    "tenacity",
    "ulid",
):
    hiddenimports += _safe(collect_submodules, pkg)


# ---------------------------------------------------------------------------
# data files & native libraries
# ---------------------------------------------------------------------------

datas = []
# certifi ships the CA bundle as a data file; httpx needs it for TLS
datas += _safe(collect_data_files, "certifi")

binaries = []
# psutil has C extensions on every platform
binaries += _safe(collect_dynamic_libs, "psutil")


# ---------------------------------------------------------------------------
# platform-specific extras
# ---------------------------------------------------------------------------

if sys.platform == "win32":
    hiddenimports += [
        "win32crypt",
        "win32api",
        "win32con",
        "pywintypes",
        "winreg",
    ]
    # WMI lives on top of pywin32 — pull both fully
    hiddenimports += _safe(collect_submodules, "wmi")
    hiddenimports += _safe(collect_submodules, "win32com")
    binaries += _safe(collect_dynamic_libs, "pywin32")


# ---------------------------------------------------------------------------
# Analysis / EXE
# ---------------------------------------------------------------------------

a = Analysis(
    [ENTRY],
    pathex=[str(AGENT_DIR)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "numpy",
        "pandas",
        "PIL",
        "PyQt5",
        "PyQt6",
        "PySide2",
        "PySide6",
        "IPython",
        "jupyter",
    ],
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
    name="azurscan-agent",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
