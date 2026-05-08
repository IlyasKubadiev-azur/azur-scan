"""Agent runtime configuration.

Layout on disk (per-OS):

  Windows:
    config:      C:\\ProgramData\\AzurScan\\config.yaml
    secrets:     C:\\ProgramData\\AzurScan\\credentials.bin   (DPAPI-encrypted)
    outbox:      C:\\ProgramData\\AzurScan\\outbox.sqlite3
    logs:        C:\\ProgramData\\AzurScan\\logs\\agent.log

  macOS:
    config:      /Library/Application Support/AzurScan/config.yaml
    secrets:     System Keychain (service: com.azurscan.agent)
    outbox:      /Library/Application Support/AzurScan/outbox.sqlite3
    logs:        /Library/Logs/AzurScan/agent.log

  Linux / dev:
    All files under ~/.azurscan/  (no privileged install required for testing).
"""
from __future__ import annotations

import os
import platform
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml


# ---------------------------------------------------------------------------
# OS-specific paths
# ---------------------------------------------------------------------------

def is_windows() -> bool: return sys.platform == "win32"
def is_macos() -> bool: return sys.platform == "darwin"


def _data_dir() -> Path:
    """Where the agent persists config, outbox and logs."""
    override = os.environ.get("AZURSCAN_DATA_DIR")
    if override:
        return Path(override)
    if is_windows():
        return Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "AzurScan"
    if is_macos():
        return Path("/Library/Application Support/AzurScan")
    # Linux/dev fallback — user-local for unprivileged testing
    return Path.home() / ".azurscan"


def _log_dir() -> Path:
    if is_macos():
        return Path("/Library/Logs/AzurScan")
    return _data_dir() / "logs"


DATA_DIR: Path = _data_dir()
LOG_DIR: Path = _log_dir()
CONFIG_PATH: Path = DATA_DIR / "config.yaml"
OUTBOX_PATH: Path = DATA_DIR / "outbox.sqlite3"
SECRETS_FILE: Path = DATA_DIR / "credentials.bin"  # used on Win + Linux fallback
LOG_FILE: Path = LOG_DIR / "agent.log"


def ensure_dirs() -> None:
    """Create data/log dirs if missing. Service installer pre-creates them
    with proper permissions; this is for first-run / dev convenience."""
    for d in (DATA_DIR, LOG_DIR):
        d.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Config schema
# ---------------------------------------------------------------------------

@dataclass
class AgentConfig:
    server_url: str = ""
    heartbeat_interval_s: int = 90
    full_scan_interval_h: int = 6
    log_level: str = "INFO"
    verify_tls: bool = True

    # Stored after enrollment (NOT credentials — those go into the secret store).
    device_id: str = ""

    @classmethod
    def load(cls) -> "AgentConfig":
        if not CONFIG_PATH.exists():
            return cls()
        try:
            data = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            return cls()
        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})

    def save(self) -> None:
        ensure_dirs()
        payload = {
            "server_url": self.server_url,
            "heartbeat_interval_s": self.heartbeat_interval_s,
            "full_scan_interval_h": self.full_scan_interval_h,
            "log_level": self.log_level,
            "verify_tls": self.verify_tls,
            "device_id": self.device_id,
        }
        CONFIG_PATH.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def platform_label() -> str:
    if is_windows(): return "windows"
    if is_macos(): return "macos"
    return "linux"
