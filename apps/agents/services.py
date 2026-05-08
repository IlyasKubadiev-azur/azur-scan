"""Agent lifecycle services: enrollment, command queueing, command ack.

Tokenless enrollment: any reachable agent can register with the server.
Idempotent on `machine_id` — re-enrollment of the same machine swaps its
credentials in place instead of creating duplicates.
"""
from __future__ import annotations

import uuid
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, NotFound

from apps.agents.models import Agent, AgentCommand
from apps.agents.tokens import sign_agent_jwt
from apps.assets.models import Asset


class EnrollmentError(APIException):
    status_code = 400
    default_detail = "enrollment_invalid"
    default_code = "agent.enrollment.invalid"


@transaction.atomic
def enroll_agent(*, fingerprint: dict) -> dict:
    """Register a machine and issue agent credentials.

    Idempotent on `machine_id` — an existing record is updated and gets fresh
    JTIs; previously issued tokens immediately become invalid.
    """
    machine_id = fingerprint.get("machine_id")
    if not machine_id:
        raise EnrollmentError(detail="machine_id_required")

    existing = Agent.objects.select_for_update().filter(machine_id=machine_id).first()

    if existing:
        agent = existing
        agent.is_revoked = False
        agent.revoked_at = None
        agent.revoked_reason = ""
        agent.os_kind = fingerprint.get("os_kind", agent.os_kind)
        agent.agent_version = fingerprint.get("agent_version", "")
        agent.public_key_fingerprint = fingerprint.get("public_key_fingerprint", "")
        if fingerprint.get("hostname"):
            agent.asset.hostname = fingerprint["hostname"]
            agent.asset.save(update_fields=["hostname", "updated_at"])
    else:
        asset = Asset.objects.create(
            hostname=fingerprint.get("hostname", "unknown"),
            is_manual=False,
            status=Asset.Status.UNKNOWN,
        )
        agent = Agent.objects.create(
            asset=asset,
            machine_id=machine_id,
            os_kind=fingerprint.get("os_kind", Agent.OSKind.WINDOWS),
            agent_version=fingerprint.get("agent_version", ""),
            public_key_fingerprint=fingerprint.get("public_key_fingerprint", ""),
        )

    access_jti = uuid.uuid4().hex
    refresh_jti = uuid.uuid4().hex
    access_token = sign_agent_jwt(
        device_id=str(agent.id), jti=access_jti,
        kind="agent_access", ttl=settings.AGENT_ACCESS_TOKEN_TTL,
    )
    refresh_token = sign_agent_jwt(
        device_id=str(agent.id), jti=refresh_jti,
        kind="agent_refresh", ttl=settings.AGENT_REFRESH_TOKEN_TTL,
    )

    agent.jwt_jti = access_jti
    agent.refresh_jti = refresh_jti
    agent.enrolled_at = timezone.now()
    agent.save()

    return {
        "device_id": str(agent.id),
        "access_token": access_token,
        "refresh_token": refresh_token,
        "config": {
            "heartbeat_s": settings.AGENT_HEARTBEAT_INTERVAL_S,
            "full_scan_h": settings.AGENT_FULL_SCAN_INTERVAL_H,
        },
    }


def issue_rescan_command(*, agent: Agent, requested_by, params: dict | None = None) -> AgentCommand:
    return AgentCommand.objects.create(
        agent=agent,
        type=AgentCommand.Type.RESCAN,
        params=params or {},
        expires_at=timezone.now() + timedelta(hours=24),
        created_by=requested_by if getattr(requested_by, "is_authenticated", False) else None,
    )


@transaction.atomic
def collect_pending_commands(*, agent: Agent, limit: int = 20) -> list[AgentCommand]:
    """Return queued commands and atomically transition them to DISPATCHED."""
    now = timezone.now()

    AgentCommand.objects.filter(
        agent=agent,
        status=AgentCommand.Status.QUEUED,
        expires_at__lt=now,
    ).update(status=AgentCommand.Status.EXPIRED)

    queued_ids = list(
        AgentCommand.objects
        .filter(agent=agent, status=AgentCommand.Status.QUEUED)
        .order_by("created_at")
        .values_list("id", flat=True)[:limit]
    )

    if not queued_ids:
        return []

    AgentCommand.objects.filter(id__in=queued_ids).update(
        status=AgentCommand.Status.DISPATCHED,
        dispatched_at=now,
    )
    return list(AgentCommand.objects.filter(id__in=queued_ids).order_by("created_at"))


def acknowledge_command(*, agent: Agent, command_id, result: dict | None = None) -> AgentCommand:
    cmd = AgentCommand.objects.filter(id=command_id, agent=agent).first()
    if cmd is None:
        raise NotFound("command_not_found")
    cmd.status = AgentCommand.Status.ACKED
    cmd.acked_at = timezone.now()
    if result is not None:
        cmd.result = result
    cmd.save(update_fields=["status", "acked_at", "result", "updated_at"])
    return cmd


def revoke_agent(*, agent: Agent, reason: str = "manual_revocation") -> Agent:
    agent.is_revoked = True
    agent.revoked_at = timezone.now()
    agent.revoked_reason = reason
    agent.jwt_jti = ""
    agent.refresh_jti = ""
    agent.save(update_fields=[
        "is_revoked", "revoked_at", "revoked_reason",
        "jwt_jti", "refresh_jti", "updated_at",
    ])
    return agent
