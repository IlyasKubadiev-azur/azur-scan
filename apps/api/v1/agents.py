"""Agent-facing endpoints: enroll, heartbeat, scan upload, command ack, token refresh."""
from __future__ import annotations

import uuid

import jwt as pyjwt
from django.conf import settings
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import (
    api_view, authentication_classes, permission_classes, throttle_classes,
)
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.agents.auth import AgentJWTAuthentication
from apps.agents.models import Agent
from apps.agents.permissions import IsAgent
from apps.agents.services import (
    acknowledge_command, collect_pending_commands, enroll_agent,
)
from apps.agents.tokens import sign_agent_jwt, verify_agent_jwt
from apps.api.throttles import AgentThrottle, EnrollThrottle
from apps.api.v1.serializers.agents import (
    CommandAckRequestSerializer, EnrollmentRequestSerializer,
    EnrollmentResponseSerializer, HeartbeatRequestSerializer,
    HeartbeatResponseSerializer, ScanUploadSerializer,
    TokenRefreshRequestSerializer, TokenRefreshResponseSerializer,
)
from apps.scanning.services import ingest_scan


# ---------------------------------------------------------------------------
# Enroll
# ---------------------------------------------------------------------------

@extend_schema(
    request=EnrollmentRequestSerializer,
    responses={201: EnrollmentResponseSerializer},
    auth=[],
)
@api_view(["POST"])
@permission_classes([AllowAny])
@authentication_classes([])
@throttle_classes([EnrollThrottle])
def enroll(request):
    serializer = EnrollmentRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    result = enroll_agent(fingerprint=serializer.validated_data["fingerprint"])
    return Response(
        EnrollmentResponseSerializer(result).data,
        status=status.HTTP_201_CREATED,
    )


# ---------------------------------------------------------------------------
# Heartbeat
# ---------------------------------------------------------------------------

@extend_schema(
    request=HeartbeatRequestSerializer,
    responses={200: HeartbeatResponseSerializer},
)
@api_view(["POST"])
@authentication_classes([AgentJWTAuthentication])
@permission_classes([IsAgent])
@throttle_classes([AgentThrottle])
def heartbeat(request):
    agent: Agent = request.auth
    serializer = HeartbeatRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    now = timezone.now()
    update_fields = ["last_heartbeat_at", "updated_at"]
    agent.last_heartbeat_at = now
    if data.get("agent_version"):
        agent.agent_version = data["agent_version"]
        update_fields.append("agent_version")
    agent.save(update_fields=update_fields)

    commands = collect_pending_commands(agent=agent)

    return Response({
        "now": now,
        "commands": [
            {"id": str(c.id), "type": c.type, "params": c.params}
            for c in commands
        ],
    })


# ---------------------------------------------------------------------------
# Scan upload
# ---------------------------------------------------------------------------

@extend_schema(
    request=ScanUploadSerializer,
    responses={201: dict},
)
@api_view(["POST"])
@authentication_classes([AgentJWTAuthentication])
@permission_classes([IsAgent])
@throttle_classes([AgentThrottle])
def scan(request):
    agent: Agent = request.auth
    serializer = ScanUploadSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    session = ingest_scan(
        agent=agent,
        raw_payload=serializer.validated_data,
        source=serializer.validated_data.get("source") or "scheduled",
    )
    return Response(
        {"accepted": True, "scan_id": str(session.id)},
        status=status.HTTP_201_CREATED,
    )


# ---------------------------------------------------------------------------
# Command ack
# ---------------------------------------------------------------------------

@extend_schema(
    request=CommandAckRequestSerializer,
    responses={200: dict},
)
@api_view(["POST"])
@authentication_classes([AgentJWTAuthentication])
@permission_classes([IsAgent])
@throttle_classes([AgentThrottle])
def command_ack(request, command_id):
    agent: Agent = request.auth
    serializer = CommandAckRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    cmd = acknowledge_command(
        agent=agent,
        command_id=command_id,
        result=serializer.validated_data.get("result") or {},
    )
    return Response({"ok": True, "id": str(cmd.id), "status": cmd.status})


# ---------------------------------------------------------------------------
# Token refresh
# ---------------------------------------------------------------------------

@extend_schema(
    request=TokenRefreshRequestSerializer,
    responses={200: TokenRefreshResponseSerializer},
    auth=[],
)
@api_view(["POST"])
@permission_classes([AllowAny])
@authentication_classes([])
def token_refresh(request):
    serializer = TokenRefreshRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    refresh = serializer.validated_data["refresh_token"]

    try:
        payload = verify_agent_jwt(refresh)
    except pyjwt.PyJWTError:
        return Response(
            {"error": {"code": "invalid_refresh_token", "message": "invalid"}},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    if payload.get("kind") != "agent_refresh":
        return Response(
            {"error": {"code": "wrong_token_kind", "message": "expected refresh"}},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    agent = Agent.objects.filter(
        id=payload["device_id"],
        refresh_jti=payload["jti"],
        is_revoked=False,
    ).first()
    if not agent:
        return Response(
            {"error": {"code": "agent_unknown_or_revoked", "message": "re-enroll required"}},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    new_jti = uuid.uuid4().hex
    new_access = sign_agent_jwt(
        device_id=str(agent.id),
        jti=new_jti,
        kind="agent_access",
        ttl=settings.AGENT_ACCESS_TOKEN_TTL,
    )
    Agent.objects.filter(id=agent.id).update(jwt_jti=new_jti)
    return Response({"access_token": new_access})
