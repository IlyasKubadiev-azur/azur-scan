"""Cross-platform secret storage for agent JWTs.

Strategy:
  Windows: DPAPI (`win32crypt.CryptProtectData`) with machine scope.
           Encrypted blob in `credentials.bin`. Only the LocalSystem account
           (or the account that encrypted it, depending on flag) can decrypt.
  macOS:   System Keychain via `/usr/bin/security` CLI. Service name is
           `com.azurscan.agent`, account names are `access` / `refresh`.
  Linux/dev: plain JSON file with permissions 0600. Not cryptographically
             protected — fine for testing but flagged on enrollment.
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
from pathlib import Path

from .config import SECRETS_FILE, ensure_dirs

KEYCHAIN_SERVICE = "com.azurscan.agent"


def store_credentials(access_token: str, refresh_token: str) -> None:
    if sys.platform == "win32":
        _store_windows({"access": access_token, "refresh": refresh_token})
    elif sys.platform == "darwin":
        _store_macos("access", access_token)
        _store_macos("refresh", refresh_token)
    else:
        _store_plain({"access": access_token, "refresh": refresh_token})


def load_credentials() -> dict:
    if sys.platform == "win32":
        return _load_windows()
    if sys.platform == "darwin":
        return {
            "access": _load_macos("access"),
            "refresh": _load_macos("refresh"),
        }
    return _load_plain()


def update_access_token(new_access: str) -> None:
    creds = load_credentials()
    store_credentials(access_token=new_access, refresh_token=creds.get("refresh", ""))


def clear_credentials() -> None:
    if sys.platform == "darwin":
        for account in ("access", "refresh"):
            subprocess.run(
                ["security", "delete-generic-password",
                 "-s", KEYCHAIN_SERVICE, "-a", account],
                capture_output=True,
            )
    else:
        try:
            SECRETS_FILE.unlink()
        except FileNotFoundError:
            pass


# ---------------------------------------------------------------------------
# Windows DPAPI
# ---------------------------------------------------------------------------

def _store_windows(payload: dict) -> None:
    ensure_dirs()
    blob = _dpapi_encrypt(json.dumps(payload).encode("utf-8"))
    SECRETS_FILE.write_bytes(blob)
    try:
        os.chmod(SECRETS_FILE, 0o600)
    except OSError:
        pass


def _load_windows() -> dict:
    if not SECRETS_FILE.exists():
        return {}
    try:
        plain = _dpapi_decrypt(SECRETS_FILE.read_bytes())
        return json.loads(plain.decode("utf-8"))
    except Exception:
        return {}


def _dpapi_encrypt(data: bytes) -> bytes:
    import win32crypt  # type: ignore
    # CRYPTPROTECT_LOCAL_MACHINE = 0x4 — any process on this machine can decrypt
    return win32crypt.CryptProtectData(data, "azurscan", None, None, None, 0x4)


def _dpapi_decrypt(blob: bytes) -> bytes:
    import win32crypt  # type: ignore
    _desc, plain = win32crypt.CryptUnprotectData(blob, None, None, None, 0x4)
    return plain


# ---------------------------------------------------------------------------
# macOS Keychain
# ---------------------------------------------------------------------------

def _store_macos(account: str, value: str) -> None:
    # Delete any existing item first (idempotent update)
    subprocess.run(
        ["security", "delete-generic-password",
         "-s", KEYCHAIN_SERVICE, "-a", account],
        capture_output=True,
    )
    subprocess.run(
        ["security", "add-generic-password",
         "-s", KEYCHAIN_SERVICE,
         "-a", account,
         "-w", value,
         "-T", "",  # no app trust list — only the storing process can read
         "-U"],
        check=True,
        capture_output=True,
    )


def _load_macos(account: str) -> str:
    res = subprocess.run(
        ["security", "find-generic-password",
         "-s", KEYCHAIN_SERVICE, "-a", account, "-w"],
        capture_output=True, text=True,
    )
    if res.returncode != 0:
        return ""
    return res.stdout.strip()


# ---------------------------------------------------------------------------
# Plain file (Linux / dev)
# ---------------------------------------------------------------------------

def _store_plain(payload: dict) -> None:
    ensure_dirs()
    SECRETS_FILE.write_text(
        base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii"),
        encoding="utf-8",
    )
    try:
        os.chmod(SECRETS_FILE, 0o600)
    except OSError:
        pass


def _load_plain() -> dict:
    if not SECRETS_FILE.exists():
        return {}
    try:
        raw = base64.b64decode(SECRETS_FILE.read_text(encoding="utf-8"))
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return {}
