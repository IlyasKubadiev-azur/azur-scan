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
    display_version = ""
    edition = ""

    if sys.platform == "win32":
        # platform.release() returns "10" / "11"; build comes from ver
        try:
            ver = platform.win32_ver()
            name = "Windows"
            version = ver[0] or version
            build = ver[1] or build
        except Exception:
            pass
        # Feature update (24H2, 25H2…) and edition (Pro/Enterprise/Home)
        # live under HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion.
        # platform.win32_ver() does NOT expose them, hence the registry read.
        try:
            import winreg
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Windows NT\CurrentVersion",
                0,
                winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
            ) as k:
                def _rd(name: str) -> str:
                    try:
                        v, _ = winreg.QueryValueEx(k, name)
                        return str(v).strip()
                    except OSError:
                        return ""
                # DisplayVersion: "24H2", "25H2" (Win10 1909+ / Win11 22H2+)
                # Fallback to ReleaseId (older builds: "1909", "2009"…)
                display_version = _rd("DisplayVersion") or _rd("ReleaseId")
                # EditionID: "Professional", "Enterprise", "Core"
                # ProductName: full marketing name with edition
                edition = _rd("EditionID") or _rd("ProductName")
                # If we don't have build yet, take CurrentBuild + UBR
                if not build:
                    cb = _rd("CurrentBuild")
                    ubr = _rd("UBR")
                    if cb:
                        build = f"{cb}.{ubr}" if ubr else cb
        except Exception:
            pass

    elif sys.platform == "darwin":
        try:
            ver, _, _ = platform.mac_ver()
            name = "macOS"
            version = ver or version
            # macOS marketing names by major version
            major = (ver or "").split(".")[0]
            display_version = {
                "11": f"Big Sur {ver}", "12": f"Monterey {ver}",
                "13": f"Ventura {ver}", "14": f"Sonoma {ver}",
                "15": f"Sequoia {ver}", "26": f"Tahoe {ver}",
            }.get(major, ver)
        except Exception:
            pass

    return {
        "name": name,
        "version": version,
        "build": build,
        "arch": arch,
        "display_version": display_version,
        "edition": edition,
    }


# ---------------------------------------------------------------------------
# Hardware
# ---------------------------------------------------------------------------

def _collect_hardware() -> dict:
    cpu_model = _cpu_model()
    cpu = {
        "model": cpu_model,
        "vendor": _cpu_vendor(cpu_model),
        "cores": psutil.cpu_count(logical=False) or None,
        "threads": psutil.cpu_count(logical=True) or None,
        "base_ghz": _cpu_base_ghz(),
        "arch": platform.machine() or "",
    }
    ram_total_mb = int(psutil.virtual_memory().total / (1024 * 1024))

    manufacturer = model = serial = gpu = ""
    motherboard = {"manufacturer": "", "product": "", "serial": ""}
    bios = {"vendor": "", "version": "", "release_date": ""}

    if sys.platform == "win32":
        manufacturer, model, serial, motherboard, bios, gpu = _hw_windows()
    elif sys.platform == "darwin":
        manufacturer, model, serial, motherboard, bios, gpu = _hw_macos()

    return {
        "cpu": cpu,
        "ram_total_mb": ram_total_mb,
        "motherboard": motherboard,
        "bios": bios,
        "gpu": gpu,
        "manufacturer": manufacturer,
        "model": model,
        "serial_number": serial,
    }


def _cpu_vendor(model: str) -> str:
    """Infer vendor from CPU model string (most reliable cross-platform)."""
    lower = (model or "").lower()
    if "intel" in lower or "xeon" in lower or "pentium" in lower or "celeron" in lower:
        return "Intel"
    if "amd" in lower or "ryzen" in lower or "epyc" in lower or "threadripper" in lower:
        return "AMD"
    if "apple" in lower or lower.startswith("m1") or lower.startswith("m2") \
            or lower.startswith("m3") or lower.startswith("m4"):
        return "Apple"
    if "qualcomm" in lower or "snapdragon" in lower:
        return "Qualcomm"
    return ""


def _cpu_base_ghz() -> float | None:
    """Best-effort base clock in GHz."""
    try:
        freq = psutil.cpu_freq()
        # `freq.max` is the rated max (== base on most modern CPUs); MHz → GHz
        if freq and freq.max:
            return round(freq.max / 1000.0, 2)
    except Exception:
        pass
    return None


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


def _hw_windows() -> tuple[str, str, str, dict, dict, str]:
    """Returns (manufacturer, model, serial, motherboard{}, bios{}, gpu)."""
    motherboard = {"manufacturer": "", "product": "", "serial": ""}
    bios_info = {"vendor": "", "version": "", "release_date": ""}
    manufacturer = model = serial = gpu = ""

    try:
        import wmi  # type: ignore
        c = wmi.WMI()
        bios = c.Win32_BIOS()[0] if c.Win32_BIOS() else None
        cs = c.Win32_ComputerSystem()[0] if c.Win32_ComputerSystem() else None
        bb = c.Win32_BaseBoard()[0] if c.Win32_BaseBoard() else None
        gpus = c.Win32_VideoController()

        if cs:
            manufacturer = (cs.Manufacturer or "").strip()
            model = (cs.Model or "").strip()
        if bios:
            serial = (bios.SerialNumber or "").strip()
            bios_info = {
                "vendor": (bios.Manufacturer or "").strip(),
                # SMBIOSBIOSVersion is what Windows shows in `msinfo32`
                "version": (getattr(bios, "SMBIOSBIOSVersion", None)
                            or bios.Version or "").strip(),
                # ReleaseDate format is YYYYMMDDHHMMSS.000000+ZZZ — keep first 8
                "release_date": _format_wmi_date(getattr(bios, "ReleaseDate", "")),
            }
        if bb:
            motherboard = {
                "manufacturer": (bb.Manufacturer or "").strip(),
                "product": (bb.Product or "").strip(),
                "serial": (bb.SerialNumber or "").strip(),
            }
        if gpus:
            gpu = "; ".join(g.Name for g in gpus if g.Name)

        return manufacturer, model, serial, motherboard, bios_info, gpu
    except Exception:
        # Fallback: WMIC (deprecated, but still on most installs)
        try:
            manufacturer = _wmic("computersystem", "get", "manufacturer")
            model = _wmic("computersystem", "get", "model")
            serial = _wmic("bios", "get", "serialnumber")
            bios_info["version"] = _wmic("bios", "get", "smbiosbiosversion")
            return manufacturer.strip(), model.strip(), serial.strip(), \
                motherboard, bios_info, ""
        except Exception:
            return "", "", "", motherboard, bios_info, ""


def _format_wmi_date(s: str) -> str:
    """WMI dates look like '20240612000000.000000+180'. Return YYYY-MM-DD."""
    s = (s or "").strip()
    if len(s) >= 8 and s[:8].isdigit():
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"
    return s


def _hw_macos() -> tuple[str, str, str, dict, dict, str]:
    """Returns (manufacturer, model, serial, motherboard{}, bios{}, gpu)."""
    motherboard = {"manufacturer": "", "product": "", "serial": ""}
    bios_info = {"vendor": "", "version": "", "release_date": ""}
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
        # Macs don't have a separate "motherboard" SKU — use Model Identifier.
        motherboard["manufacturer"] = "Apple"
        motherboard["product"] = kv.get("Model Identifier", "")
        # Boot ROM (firmware) version is the macOS equivalent of BIOS version.
        bios_info["vendor"] = "Apple"
        bios_info["version"] = kv.get("System Firmware Version", "") \
            or kv.get("Boot ROM Version", "")

        try:
            gpu_out = subprocess.run(
                ["system_profiler", "SPDisplaysDataType"],
                capture_output=True, text=True, timeout=10, check=True,
            ).stdout
            gpu_match = re.search(r"Chipset Model: (.+)", gpu_out)
            gpu = gpu_match.group(1).strip() if gpu_match else ""
        except Exception:
            gpu = ""
        return manufacturer, model, serial, motherboard, bios_info, gpu
    except Exception:
        return "Apple", "", "", motherboard, bios_info, ""


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
