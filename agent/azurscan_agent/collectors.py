"""Cross-platform fact collectors.

Each collector is best-effort: on failure it returns an empty/partial result
and stashes the error in the global `errors` dict that the runtime ships in
the scan payload (so the backend can see what failed without losing the rest).
"""
from __future__ import annotations

import logging
import platform
import re
import shutil
import socket
import subprocess
import sys
from typing import Any

import psutil

from . import __version__
from .machine import fqdn, hostname, machine_id, os_kind

log = logging.getLogger(__name__)


def collect_all() -> tuple[dict[str, Any], dict[str, str]]:
    """Run every collector. Return (payload, errors)."""
    errors: dict[str, str] = {}
    out: dict[str, Any] = {}

    out["scan_id"] = ""  # filled in by caller (ulid)
    out["agent_version"] = __version__

    out["system"] = _safe(_collect_system, errors, "system")
    out["os"] = _safe(_collect_os, errors, "os")
    out["hardware"] = _safe(_collect_hardware, errors, "hardware")
    out["storage"] = _safe(_collect_storage, errors, "storage")
    out["network"] = _safe(_collect_network, errors, "network")
    out["errors"] = errors
    return out, errors


def _safe(fn, errors: dict, name: str) -> Any:
    try:
        return fn()
    except Exception as exc:  # pragma: no cover — defensive
        log.exception("collector %s failed", name)
        errors[name] = f"{type(exc).__name__}: {exc}"
        return {}


# ---------------------------------------------------------------------------
# System
# ---------------------------------------------------------------------------

def _collect_system() -> dict:
    return {
        "hostname": hostname(),
        "fqdn": fqdn(),
        "machine_id": machine_id(),
        "current_user": _current_user(),
        "last_logged_user": _last_logged_user(),
    }


def _current_user() -> str:
    try:
        users = psutil.users()
        return users[0].name if users else ""
    except Exception:
        return ""


def _last_logged_user() -> str:
    """Best effort. On Windows we read it from registry; macOS from `last`.
    Stub for now — return empty if unavailable."""
    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\Authentication\LogonUI",
            ) as k:
                val, _ = winreg.QueryValueEx(k, "LastLoggedOnUser")
                return str(val).split("\\")[-1]
        except OSError:
            return ""
    return ""


# ---------------------------------------------------------------------------
# OS
# ---------------------------------------------------------------------------

def _collect_os() -> dict:
    name = platform.system()
    version = platform.release()
    build = platform.version()
    arch = platform.machine()
    if sys.platform == "win32":
        # platform.release() returns "10" / "11"; build comes from ver
        try:
            ver = platform.win32_ver()
            name = "Windows"
            version = ver[0] or version
            build = ver[1] or build
        except Exception:
            pass
    elif sys.platform == "darwin":
        try:
            ver, _, _ = platform.mac_ver()
            name = "macOS"
            version = ver or version
        except Exception:
            pass
    return {
        "name": name,
        "version": version,
        "build": build,
        "arch": arch,
    }


# ---------------------------------------------------------------------------
# Hardware
# ---------------------------------------------------------------------------

def _collect_hardware() -> dict:
    cpu = {
        "model": _cpu_model(),
        "cores": psutil.cpu_count(logical=False) or None,
        "threads": psutil.cpu_count(logical=True) or None,
    }
    ram_total_mb = int(psutil.virtual_memory().total / (1024 * 1024))

    manufacturer = ""
    model = ""
    serial = ""
    motherboard = ""
    gpu = ""

    if sys.platform == "win32":
        manufacturer, model, serial, motherboard, gpu = _hw_windows()
    elif sys.platform == "darwin":
        manufacturer, model, serial, motherboard, gpu = _hw_macos()

    return {
        "cpu": cpu,
        "ram_total_mb": ram_total_mb,
        "motherboard": motherboard,
        "gpu": gpu,
        "manufacturer": manufacturer,
        "model": model,
        "serial_number": serial,
    }


def _cpu_model() -> str:
    if sys.platform == "win32":
        try:
            return _wmic("cpu", "get", "name").strip()
        except Exception:
            pass
    if sys.platform == "darwin":
        try:
            return subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True, text=True, timeout=5, check=True,
            ).stdout.strip()
        except Exception:
            pass
    return platform.processor() or ""


def _hw_windows() -> tuple[str, str, str, str, str]:
    try:
        import wmi  # type: ignore
        c = wmi.WMI()
        bios = c.Win32_BIOS()[0] if c.Win32_BIOS() else None
        cs = c.Win32_ComputerSystem()[0] if c.Win32_ComputerSystem() else None
        bb = c.Win32_BaseBoard()[0] if c.Win32_BaseBoard() else None
        gpus = c.Win32_VideoController()
        manufacturer = (cs.Manufacturer or "") if cs else ""
        model = (cs.Model or "") if cs else ""
        serial = (bios.SerialNumber or "") if bios else ""
        motherboard = ((bb.Manufacturer or "") + " " + (bb.Product or "")).strip() if bb else ""
        gpu = "; ".join(g.Name for g in gpus if g.Name) if gpus else ""
        return manufacturer.strip(), model.strip(), serial.strip(), motherboard, gpu
    except Exception:
        # Fallback: WMIC (deprecated, but still on most installs)
        try:
            manufacturer = _wmic("computersystem", "get", "manufacturer")
            model = _wmic("computersystem", "get", "model")
            serial = _wmic("bios", "get", "serialnumber")
            return manufacturer.strip(), model.strip(), serial.strip(), "", ""
        except Exception:
            return "", "", "", "", ""


def _hw_macos() -> tuple[str, str, str, str, str]:
    try:
        out = subprocess.run(
            ["system_profiler", "SPHardwareDataType"],
            capture_output=True, text=True, timeout=10, check=True,
        ).stdout
        kv: dict[str, str] = {}
        for line in out.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                kv[k.strip()] = v.strip()
        manufacturer = "Apple"
        model = kv.get("Model Name", "") or kv.get("Model Identifier", "")
        serial = kv.get("Serial Number (system)", "") or kv.get("Hardware UUID", "")
        # GPU
        try:
            gpu_out = subprocess.run(
                ["system_profiler", "SPDisplaysDataType"],
                capture_output=True, text=True, timeout=10, check=True,
            ).stdout
            gpu_match = re.search(r"Chipset Model: (.+)", gpu_out)
            gpu = gpu_match.group(1).strip() if gpu_match else ""
        except Exception:
            gpu = ""
        return manufacturer, model, serial, "", gpu
    except Exception:
        return "Apple", "", "", "", ""


def _wmic(*args) -> str:
    """Run wmic, strip header line and return value."""
    res = subprocess.run(
        ["wmic", *args],
        capture_output=True, text=True, timeout=15, check=True,
    )
    lines = [l.strip() for l in res.stdout.splitlines() if l.strip()]
    # Drop header
    return lines[1] if len(lines) >= 2 else ""


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

def _collect_storage() -> dict:
    disks = []
    for p in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(p.mountpoint)
            disks.append({
                "device": p.device,
                "model": "",
                "size_bytes": usage.total,
                "free_bytes": usage.free,
                "fs_type": p.fstype,
                "mount_point": p.mountpoint,
            })
        except (PermissionError, OSError):
            continue
    return {"disks": disks}


# ---------------------------------------------------------------------------
# Network
# ---------------------------------------------------------------------------

def _collect_network() -> dict:
    addrs = psutil.net_if_addrs()
    stats = psutil.net_if_stats()
    interfaces = []
    primary_picked = False

    for name, family_addrs in addrs.items():
        mac = ""
        ips: list[str] = []
        for a in family_addrs:
            if a.family == psutil.AF_LINK:
                mac = (a.address or "").upper()
            elif a.family == socket.AF_INET:
                ips.append(a.address)
            elif a.family == socket.AF_INET6:
                # strip zone id (eg "fe80::1%eth0")
                ips.append(a.address.split("%")[0])

        if not mac:
            continue  # skip pseudo-interfaces (loopback etc.)
        if mac in ("00:00:00:00:00:00",):
            continue

        is_up = stats[name].isup if name in stats else False
        is_primary = False
        if not primary_picked and is_up and any(
            ip and not ip.startswith("127.") and not ip.startswith("169.254.") for ip in ips
        ):
            is_primary = True
            primary_picked = True

        interfaces.append({
            "name": name,
            "mac_address": mac,
            "ip_addresses": ips,
            "is_primary": is_primary,
        })
    return {"interfaces": interfaces}
