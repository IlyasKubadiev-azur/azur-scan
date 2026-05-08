"""Agent JWT signing / verification.

Uses HS256 with a server-side secret (`AGENT_JWT_SECRET`). Agents never need to
verify the token themselves — they treat it as opaque — so a symmetric secret
is sufficient and simpler than asymmetric keys for MVP. All app servers must
share the same secret.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone as dt_timezone

import jwt
from django.conf import settings


def sign_agent_jwt(*, device_id: str, jti: str, kind: str, ttl: timedelta) -> str:
    now = datetime.now(dt_timezone.utc)
    payload = {
        "iss": "azur-scan",
        "sub": device_id,
        "kind": kind,  # "agent_access" or "agent_refresh"
        "device_id": device_id,
        "jti": jti,
        "iat": int(now.timestamp()),
        "exp": int((now + ttl).timestamp()),
    }
    return jwt.encode(payload, settings.AGENT_JWT_SECRET, algorithm="HS256")


def verify_agent_jwt(token: str) -> dict:
    return jwt.decode(
        token,
        settings.AGENT_JWT_SECRET,
        algorithms=["HS256"],
        issuer="azur-scan",
    )
