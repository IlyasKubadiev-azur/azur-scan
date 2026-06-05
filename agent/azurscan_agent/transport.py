"""HTTP transport: enroll, heartbeat, scan upload, command ack, token refresh,
plus a SQLite-backed outbox for offline scan retries.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import time
from contextlib import closing
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from . import __version__
from .config import OUTBOX_PATH, AgentConfig, ensure_dirs
from .secrets_store import load_credentials, store_credentials, update_access_token

log = logging.getLogger(__name__)


class TransportError(Exception):
    pass


class Unauthorized(TransportError):
    """401 from server — usually means token expired/revoked."""


# ---------------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------------

class Transport:
    def __init__(self, cfg: AgentConfig):
        self.cfg = cfg
        self._client = httpx.Client(
            base_url=cfg.server_url.rstrip("/"),
            timeout=httpx.Timeout(15.0, connect=10.0),
            verify=cfg.verify_tls,
            headers={"User-Agent": f"azurscan-agent/{__version__}"},
        )

    def close(self) -> None:
        self._client.close()

    # ---- enroll -------------------------------------------------------------

    def enroll(self, *, fingerprint: dict) -> dict:
        r = self._client.post(
            "/api/v1/agents/enroll",
            json={"fingerprint": fingerprint},
        )
        if r.status_code >= 400:
            raise TransportError(f"enroll failed: HTTP {r.status_code}: {r.text[:200]}")
        return r.json()

    # ---- heartbeat ----------------------------------------------------------

    def heartbeat(self, *, agent_version: str, last_scan_at: str | None = None) -> dict:
        return self._auth_call(
            "POST", "/api/v1/agents/heartbeat",
            json={"agent_version": agent_version, "last_scan_at": last_scan_at},
        )

    # ---- scan ---------------------------------------------------------------

    def upload_scan(self, payload: dict) -> dict:
        return self._auth_call("POST", "/api/v1/agents/scan", json=payload)

    # ---- command ack --------------------------------------------------------

    def ack_command(self, command_id: str, result: dict | None = None) -> dict:
        return self._auth_call(
            "POST", f"/api/v1/agents/commands/{command_id}/ack",
            json={"result": result or {}},
        )

    # ---- token refresh ------------------------------------------------------

    def refresh_access_token(self) -> str:
        creds = load_credentials()
        refresh = creds.get("refresh", "")
        if not refresh:
            raise Unauthorized("no refresh token stored — re-enroll required")
        r = self._client.post(
            "/api/v1/agents/token/refresh",
            json={"refresh_token": refresh},
        )
        if r.status_code == 401:
            raise Unauthorized("refresh token rejected — re-enroll required")
        r.raise_for_status()
        new_access = r.json()["access_token"]
        update_access_token(new_access)
        return new_access

    # ---- internals ----------------------------------------------------------

    @retry(
        retry=retry_if_exception_type(httpx.TransportError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    def _auth_call(self, method: str, path: str, **kwargs) -> dict:
        creds = load_credentials()
        access = creds.get("access", "")
        # Diagnostic fingerprint — first/last 6 chars of the token + length.
        # Helps identify "wrong/stale credentials in storage" without leaking
        # the full JWT to logs.
        if access:
            fp = f"{access[:6]}...{access[-6:]}(len={len(access)})"
        else:
            fp = "<EMPTY>"
        headers = {"Authorization": f"Bearer {access}"} if access else {}
        kwargs.setdefault("headers", {}).update(headers)

        r = self._client.request(method, path, **kwargs)
        if r.status_code == 401:
            log.warning("auth call %s %s -> 401 with token %s", method, path, fp)
            # one retry after refresh
            new_access = self.refresh_access_token()
            kwargs["headers"]["Authorization"] = f"Bearer {new_access}"
            r = self._client.request(method, path, **kwargs)
            if r.status_code == 401:
                raise Unauthorized("auth still failing after refresh")

        if r.status_code >= 400:
            raise TransportError(f"HTTP {r.status_code}: {r.text[:200]}")

        if r.headers.get("content-type", "").startswith("application/json"):
            return r.json()
        return {}


# ---------------------------------------------------------------------------
# Outbox (SQLite) — buffers scans when the server is unreachable
# ---------------------------------------------------------------------------

class Outbox:
    """Append-only queue of scan payloads with exponential backoff per row.

    Schema:
        scans(
          id INTEGER PK,
          payload TEXT NOT NULL,
          created_at REAL NOT NULL,
          attempts INTEGER NOT NULL DEFAULT 0,
          next_attempt_at REAL NOT NULL,
          poisoned INTEGER NOT NULL DEFAULT 0
        )
    """
    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS scans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        payload TEXT NOT NULL,
        created_at REAL NOT NULL,
        attempts INTEGER NOT NULL DEFAULT 0,
        next_attempt_at REAL NOT NULL,
        poisoned INTEGER NOT NULL DEFAULT 0
    );
    CREATE INDEX IF NOT EXISTS idx_scans_due
        ON scans(poisoned, next_attempt_at);
    """

    _BACKOFF_SCHEDULE = [30, 60, 300, 1800, 7200]  # 30s, 1m, 5m, 30m, 2h

    def __init__(self, path=OUTBOX_PATH):
        ensure_dirs()
        self.path = path
        with closing(sqlite3.connect(self.path)) as conn:
            conn.executescript(self._SCHEMA)
            conn.commit()

    def enqueue(self, payload: dict) -> int:
        now = time.time()
        with closing(sqlite3.connect(self.path)) as conn:
            cur = conn.execute(
                "INSERT INTO scans(payload, created_at, next_attempt_at) VALUES (?, ?, ?)",
                (json.dumps(payload), now, now),
            )
            conn.commit()
            return cur.lastrowid

    def due(self, limit: int = 10) -> list[tuple[int, dict]]:
        now = time.time()
        with closing(sqlite3.connect(self.path)) as conn:
            rows = conn.execute(
                "SELECT id, payload FROM scans "
                "WHERE poisoned = 0 AND next_attempt_at <= ? "
                "ORDER BY id LIMIT ?",
                (now, limit),
            ).fetchall()
        return [(r[0], json.loads(r[1])) for r in rows]

    def mark_sent(self, row_id: int) -> None:
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute("DELETE FROM scans WHERE id = ?", (row_id,))
            conn.commit()

    def mark_failed(self, row_id: int, *, poisoned: bool = False) -> None:
        with closing(sqlite3.connect(self.path)) as conn:
            row = conn.execute(
                "SELECT attempts FROM scans WHERE id = ?", (row_id,)
            ).fetchone()
            if not row:
                return
            attempts = row[0] + 1
            if poisoned:
                conn.execute(
                    "UPDATE scans SET attempts = ?, poisoned = 1 WHERE id = ?",
                    (attempts, row_id),
                )
            else:
                idx = min(attempts - 1, len(self._BACKOFF_SCHEDULE) - 1)
                next_at = time.time() + self._BACKOFF_SCHEDULE[idx]
                conn.execute(
                    "UPDATE scans SET attempts = ?, next_attempt_at = ? WHERE id = ?",
                    (attempts, next_at, row_id),
                )
            conn.commit()

    def stats(self) -> dict:
        with closing(sqlite3.connect(self.path)) as conn:
            total = conn.execute("SELECT COUNT(*) FROM scans").fetchone()[0]
            poisoned = conn.execute(
                "SELECT COUNT(*) FROM scans WHERE poisoned = 1"
            ).fetchone()[0]
        return {"total": total, "poisoned": poisoned, "pending": total - poisoned}
