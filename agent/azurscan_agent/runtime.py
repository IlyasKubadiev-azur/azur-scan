"""Main runtime loop.

Concurrent activities, single thread, deadline-driven:
  1. ensure_enrolled() at startup — auto-enroll if no credentials but URL is set
  2. heartbeat every cfg.heartbeat_interval_s (default 90s)
  3. full scan every cfg.full_scan_interval_h hours (default 6h) + on rescan command
  4. outbox flush every 30s while there are pending scans
"""
from __future__ import annotations

import logging
import signal
import threading
import time
from datetime import datetime, timezone

import ulid

from . import __version__
from .collectors import collect_all
from .config import AgentConfig
from .machine import hostname, machine_id, os_kind
from .secrets_store import load_credentials, store_credentials
from .transport import Outbox, Transport, TransportError, Unauthorized

log = logging.getLogger(__name__)


class Runtime:
    def __init__(self, cfg: AgentConfig):
        self.cfg = cfg
        self.transport = Transport(cfg)
        self.outbox = Outbox()
        self._stop = threading.Event()
        self._last_full_scan_at: float = 0.0

    # ------------------------------------------------------------------------
    # Enrollment
    # ------------------------------------------------------------------------

    def ensure_enrolled(self) -> bool:
        """If credentials are missing, perform tokenless enrollment.

        Returns True if the agent has valid credentials after this call.
        """
        creds = load_credentials()
        if creds.get("access") and self.cfg.device_id:
            return True

        if not self.cfg.server_url:
            log.error("ensure_enrolled: server_url not configured")
            return False

        log.info("not yet enrolled; auto-registering with %s", self.cfg.server_url)
        fingerprint = {
            "machine_id": machine_id(),
            "hostname": hostname(),
            "primary_mac": "",
            "os_kind": os_kind(),
            "agent_version": __version__,
            "public_key_fingerprint": "",
        }
        try:
            result = self.transport.enroll(fingerprint=fingerprint)
        except TransportError as exc:
            log.warning("auto-enroll failed: %s", exc)
            return False

        self.cfg.device_id = result["device_id"]
        srv_cfg = result.get("config") or {}
        self.cfg.heartbeat_interval_s = int(srv_cfg.get("heartbeat_s", self.cfg.heartbeat_interval_s))
        self.cfg.full_scan_interval_h = int(srv_cfg.get("full_scan_h", self.cfg.full_scan_interval_h))
        self.cfg.save()
        store_credentials(
            access_token=result["access_token"],
            refresh_token=result["refresh_token"],
        )
        log.info("enrolled successfully; device_id=%s", self.cfg.device_id)
        return True

    # ------------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------------

    def run(self) -> None:
        self._install_signal_handlers()
        log.info("agent runtime starting")

        # Block until enrolled — keep retrying so that, e.g. when the backend
        # is briefly unreachable on first install, we don't crash the service.
        while not self._stop.is_set():
            if self.ensure_enrolled():
                break
            log.info("retrying enrollment in 60s")
            self._stop.wait(timeout=60)

        if self._stop.is_set():
            self.transport.close()
            return

        log.info("device_id=%s", self.cfg.device_id)
        last_heartbeat = 0.0
        last_outbox_flush = 0.0

        # First scan right after start, then on schedule
        self.do_full_scan(source="enrollment")

        while not self._stop.is_set():
            now = time.time()

            if now - last_heartbeat >= self.cfg.heartbeat_interval_s:
                self._do_heartbeat()
                last_heartbeat = now

            if now - self._last_full_scan_at >= self.cfg.full_scan_interval_h * 3600:
                self.do_full_scan()

            if now - last_outbox_flush >= 30:
                self._flush_outbox()
                last_outbox_flush = now

            self._stop.wait(timeout=5)

        log.info("agent runtime stopped")
        self.transport.close()

    def stop(self) -> None:
        self._stop.set()

    def _install_signal_handlers(self) -> None:
        def _handler(signum, frame):
            log.info("received signal %s — stopping", signum)
            self.stop()
        try:
            signal.signal(signal.SIGTERM, _handler)
            signal.signal(signal.SIGINT, _handler)
        except (ValueError, OSError):
            pass

    # ------------------------------------------------------------------------
    # Heartbeat
    # ------------------------------------------------------------------------

    def _do_heartbeat(self) -> None:
        try:
            response = self.transport.heartbeat(agent_version=__version__)
        except Unauthorized:
            log.error("heartbeat unauthorized — re-enrolling")
            self.cfg.device_id = ""
            self.cfg.save()
            from .secrets_store import clear_credentials
            clear_credentials()
            if not self.ensure_enrolled():
                log.error("re-enrollment failed; will retry next heartbeat")
            return
        except TransportError as exc:
            log.warning("heartbeat failed: %s", exc)
            return

        for cmd in response.get("commands", []):
            self._handle_command(cmd)

    # ------------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------------

    def _handle_command(self, cmd: dict) -> None:
        cid = cmd.get("id")
        ctype = cmd.get("type")
        log.info("command received: %s %s", cid, ctype)
        try:
            if ctype == "rescan":
                self.do_full_scan(source="rescan_command")
                self._safe_ack(cid, {"ok": True})
            elif ctype == "revoke":
                self._safe_ack(cid, {"ok": True})
                self.stop()
            else:
                log.warning("unknown command type: %s", ctype)
                self._safe_ack(cid, {"ok": False, "error": "unknown_command"})
        except Exception as exc:
            log.exception("command %s failed", cid)
            self._safe_ack(cid, {"ok": False, "error": str(exc)})

    def _safe_ack(self, cid: str | None, result: dict) -> None:
        if not cid:
            return
        try:
            self.transport.ack_command(cid, result)
        except TransportError as exc:
            log.warning("command ack failed for %s: %s", cid, exc)

    # ------------------------------------------------------------------------
    # Full scan
    # ------------------------------------------------------------------------

    def do_full_scan(self, source: str = "scheduled") -> None:
        log.info("running full scan (source=%s)", source)
        started_at = datetime.now(timezone.utc)

        payload, errors = collect_all()
        finished_at = datetime.now(timezone.utc)

        payload.update({
            "scan_id": str(ulid.new()),
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "source": source,
        })

        if errors:
            log.warning("scan completed with %d collector errors", len(errors))

        try:
            self.transport.upload_scan(payload)
            log.info("scan %s uploaded", payload["scan_id"])
        except Unauthorized:
            log.error("scan unauthorized — queuing and trying re-enroll on next heartbeat")
            self.outbox.enqueue(payload)
        except TransportError as exc:
            log.warning("scan upload failed: %s — queued in outbox", exc)
            self.outbox.enqueue(payload)

        self._last_full_scan_at = time.time()

    # ------------------------------------------------------------------------
    # Outbox
    # ------------------------------------------------------------------------

    def _flush_outbox(self) -> None:
        due = self.outbox.due(limit=10)
        if not due:
            return
        log.info("flushing %d queued scan(s)", len(due))
        for row_id, payload in due:
            try:
                self.transport.upload_scan(payload)
                self.outbox.mark_sent(row_id)
            except Unauthorized:
                log.error("outbox flush unauthorized — leaving in queue")
                self.outbox.mark_failed(row_id, poisoned=False)
                return
            except TransportError as exc:
                log.warning("outbox row %s still failing: %s", row_id, exc)
                poisoned = "HTTP 4" in str(exc) and "HTTP 401" not in str(exc)
                self.outbox.mark_failed(row_id, poisoned=poisoned)
