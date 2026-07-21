"""Central helper for writing to core.AuditLog.

Call `log_event(...)` from services and views instead of touching the
AuditLog model directly. Keeping the surface small means:
  - One consistent action-code taxonomy (see ACTIONS below)
  - Uniform IP / user-agent extraction from `request` if provided
  - Fail-open behaviour: audit writes NEVER raise into the caller. If the
    audit DB write fails for any reason we swallow the exception and log
    a warning — losing an audit row is better than 500-ing a live request.
"""
from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Canonical action codes. Use these constants to avoid typos and to make it
# easy to grep for "who cares about agent revocations": `git grep AGENT_REVOKED`.
# ---------------------------------------------------------------------------

# Agents
AGENT_ENROLLED       = "agent.enrolled"        # brand-new agent registration
AGENT_REENROLLED     = "agent.reenrolled"      # same machine_id, refreshed tokens
AGENT_REVOKED        = "agent.revoked"
AGENT_TOKEN_REFRESHED = "agent.token_refreshed"

# Scans / commands
SCAN_RECEIVED        = "scan.received"
COMMAND_RESCAN       = "command.rescan.issued"
COMMAND_ACKED        = "command.acked"

# Assets
ASSET_MANUAL_CREATED = "asset.manual_created"
ASSET_OWNER_CHANGED  = "asset.owner_changed"
ASSET_DELETED        = "asset.deleted"

# Users / access
USER_LOGGED_IN       = "user.logged_in"
USER_LOGGED_OUT      = "user.logged_out"
USER_LOGIN_FAILED    = "user.login_failed"


def log_event(
    *,
    action: str,
    actor: Any = None,
    object_type: str = "",
    object_id: str | int = "",
    request: Any = None,
    before: dict | None = None,
    after: dict | None = None,
) -> None:
    """Persist one AuditLog row. Never raises."""
    # Lazy import to avoid circular (core.audit is imported by apps that
    # define core.models' AuditLog's actor FK target — accounts.User).
    from apps.core.models import AuditLog

    ip = ""
    user_agent = ""
    if request is not None:
        # Trust X-Forwarded-For first (behind nginx/cloudflared), fall back
        # to REMOTE_ADDR. Take only the first hop.
        xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if xff:
            ip = xff.split(",")[0].strip()
        else:
            ip = request.META.get("REMOTE_ADDR", "") or ""
        user_agent = (request.META.get("HTTP_USER_AGENT") or "")[:512]
        # If the caller didn't pass an explicit actor, take request.user
        if actor is None and getattr(request, "user", None) is not None:
            actor = request.user

    actor_obj = actor if getattr(actor, "is_authenticated", False) else None

    try:
        AuditLog.objects.create(
            actor=actor_obj,
            action=action,
            object_type=object_type,
            object_id=str(object_id),
            ip=ip or None,
            user_agent=user_agent,
            data_before=before,
            data_after=after,
        )
    except Exception:
        log.exception("audit write failed for %s / %s / %s", action, object_type, object_id)
