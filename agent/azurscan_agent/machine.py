"""Cross-platform machine identity helpers.

`machine_id` is the stable per-device identifier we send to the backend on
enroll. The backend uses it to deduplicate when the same machine re-enrolls.
"""
from __future__ import annotations

import platform
import socket
import subprocess
import sys
import uuid
from functools import lru_cache


@lru_cache(maxsize=1)
def hostname() -> str:
    return socket.gethostname()


@lru_cache(maxsize=1)
def fqdn() -> str:
    try:
        return socket.getfqdn() or hostname()
    except Exception:
        return hostname()


@lru_cache(maxsize=1)
def machine_id() -> str:
    """Stable per-machine UUID.

    Windows: HKLM\\SOFTWARE\\Microsoft\\Cryptography\\MachineGuid
    macOS:   IOPlatformUUID via ioreg
    Linux/fallback: /etc/machine-id, then a hash of MAC + hostname.
    """
    if sys.platform == "win32":
        try:
            import winreg  # stdlib on Windows
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Cryptography",
                0,
                winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
            ) as k:
                value, _ = winreg.QueryValueEx(k, "MachineGuid")
                return str(value).strip().lower()
        except OSError:
            pass

    if sys.platform == "darwin":
        try:
            out = subprocess.run(
                ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                capture_output=True, text=True, timeout=5, check=True,
            ).stdout
            for line in out.splitlines():
                if "IOPlatformUUID" in line:
                    return line.split("=")[-1].strip().strip('"').lower()
        except (subprocess.SubprocessError, FileNotFoundError):
            pass

    # Linux / generic fallback
    for path in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
        try:
            with open(path) as f:
                content = f.read().strip()
                if content:
                    return content.lower()
        except OSError:
            continue

    # Last resort — derived from MAC + hostname (NOT cryptographically stable
    # across reinstalls, but better than nothing for dev)
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{hostname()}-{uuid.getnode():012x}"))


@lru_cache(maxsize=1)
def os_kind() -> str:
    if sys.platform == "win32": return "windows"
    if sys.platform == "darwin": return "macos"
    return "linux"
