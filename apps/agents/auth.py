"""DRF authentication for agent JWTs.

Returns ``(AnonymousUser, agent)`` on success — the agent ends up in
``request.auth``. Standard ``IsAuthenticated`` will reject these requests, so
agent endpoints use ``IsAgent`` from ``apps.agents.permissions``.
"""
from __future__ import annotations

import jwt as pyjwt
from django.contrib.auth.models import AnonymousUser
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from apps.agents.models import Agent
from apps.agents.tokens import verify_agent_jwt


class AgentJWTAuthentication(BaseAuthentication):
    keyword = "Bearer"

    def authenticate(self, request):
        auth = request.META.get("HTTP_AUTHORIZATION", "")
        if not auth.startswith(f"{self.keyword} "):
            return None
        token = auth.split(" ", 1)[1].strip()

        try:
            payload = verify_agent_jwt(token)
        except pyjwt.ExpiredSignatureError as exc:
            raise AuthenticationFailed("agent_token_expired") from exc
        except pyjwt.InvalidTokenError:
            # Not our token (could be a user JWT) — let other auth classes try.
            return None

        if payload.get("kind") != "agent_access":
            return None

        agent = (
            Agent.objects
            .select_related("asset")
            .filter(
                id=payload["device_id"],
                jwt_jti=payload["jti"],
                is_revoked=False,
            )
            .first()
        )
        if not agent:
            raise AuthenticationFailed("agent_revoked_or_unknown")

        return (AnonymousUser(), agent)

    def authenticate_header(self, request):
        return self.keyword
