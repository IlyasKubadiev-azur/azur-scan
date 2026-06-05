"""Cross-platform secret storage for agent JWTs.

Strategy:
  Windows: DPAPI (`win32crypt.CryptProtectData`) with machine scope.
           Encrypted blob in `credentials.bin`. Only the LocalSystem account
           (or the account that encrypted it, depending on flag) can decrypt.

  macOS:   0600 file in /Library/Application Support/AzurScan/credentials.bin
           owned by root:wheel. We TRIED to use System Keychain via the
           `security` CLI in v0.1.8/0.1.9 but ran into a non-debuggable
           pathology: writes appeared to succeed under LaunchDaemon root
           context, but subsequent reads returned empty strings — putting
           the runtime into an infinite enroll loop.
           Filesystem permissions give identical isolation to Keychain
           for a root-only LaunchDaemon (any other root process can read
           a System Keychain entry anyway via the same `security` CLI),
           so we lose nothing security-wise and gain predictability.

  Linux/dev: same 0600 file. Not cryptographically protected — fine for
             testing but flagged on enrollment.
"""
from __future__ import annotations

import base64
import json
import os
import sys
from pathlib import Path

from .config import SECRETS_FILE, ensure_dirs


def store_credentials(access_token: str, refresh_token: str) -> None:
    payload = {"access": access_token, "refresh": refresh_token}
    if sys.platform == "win32":
        _store_windows(payload)
    else:
        # macOS + Linux: 0600 file. See module docstring for why macOS
        # uses files instead of Keychain.
        _store_plain(payload)

    # Roundtrip verification — catch silent corruption / race conditions
    # immediately rather than burning enroll cycles later.
    rt = load_credentials()
    if rt.get("access") != access_token or rt.get("refresh") != refresh_token:
        raise RuntimeError(
            "credential write/read mismatch — storage layer is broken; "
            f"expected access len={len(access_token)} but read len={len(rt.get('access') or '')}"
        )


def load_credentials() -> dict:
    if sys.platform == "win32":
        return _load_windows()
    # macOS + Linux: file-backed
    return _load_plain()


def update_access_token(new_access: str) -> None:
    creds = load_credentials()
    store_credentials(access_token=new_access, refresh_token=creds.get("refresh", ""))


def clear_credentials() -> None:
    # macOS + Linux: just remove the file. The legacy Keychain entries
    # from v0.1.8/0.1.9 are wiped by the user-side cleanup script.
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
# 0600 file (macOS + Linux + dev)
#
# Atomic write: dump to temp file -> chmod 600 -> rename. Without atomic
# rename, a crash between truncate and write would leave us with empty
# credentials, which is what we suspect bit us in v0.1.8/v0.1.9.
# ---------------------------------------------------------------------------

def _store_plain(payload: dict) -> None:
    ensure_dirs()
    body = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")
    tmp = SECRETS_FILE.with_suffix(SECRETS_FILE.suffix + ".tmp")
    tmp.write_text(body, encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, SECRETS_FILE)  # atomic on POSIX + Windows


def _load_plain() -> dict:
    if not SECRETS_FILE.exists():
        return {}
    try:
        raw = base64.b64decode(SECRETS_FILE.read_text(encoding="utf-8"))
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return {}
