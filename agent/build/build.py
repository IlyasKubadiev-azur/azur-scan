"""Cross-platform PyInstaller driver.

Usage (from the `agent/` directory):
    python -m pip install -e ".[build]"          # install agent + pyinstaller
    python -m pip install -e ".[windows]"        # Windows extras (pywin32, wmi)
    python build/build.py

Output:
    Windows: agent/dist/azurscan-agent.exe
    macOS:   agent/dist/azurscan-agent
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parent.parent
SPEC = AGENT_DIR / "build" / "azurscan-agent.spec"
DIST = AGENT_DIR / "dist"
WORK = AGENT_DIR / "build" / "_pyinstaller_work"


def main() -> int:
    if not SPEC.exists():
        print(f"spec not found: {SPEC}", file=sys.stderr)
        return 1

    # Clean prior artifacts. Tolerate locked files (anti-virus / IDE indexer
    # may briefly hold handles); PyInstaller --noconfirm overwrites anyway.
    for path in (DIST, WORK):
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        str(SPEC),
        "--noconfirm",
        "--clean",
        "--distpath", str(DIST),
        "--workpath", str(WORK),
    ]
    print(">>", " ".join(cmd))
    rc = subprocess.call(cmd, cwd=str(AGENT_DIR))
    if rc != 0:
        return rc

    binary = "azurscan-agent.exe" if sys.platform == "win32" else "azurscan-agent"
    out = DIST / binary
    print(f"\nBuilt: {out}  ({out.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
