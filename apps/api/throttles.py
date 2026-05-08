"""Throttle classes used across the API.

Note: agent endpoints intentionally don't use the default user/anon throttles
since their auth class returns AnonymousUser. They use ``ScopedAgentThrottle``.
"""
from rest_framework.throttling import (
    AnonRateThrottle, SimpleRateThrottle, UserRateThrottle,
)


class BurstAnonThrottle(AnonRateThrottle):
    scope = "anon"


class UserScopedThrottle(UserRateThrottle):
    scope = "user"


class EnrollThrottle(AnonRateThrottle):
    """Aggressive throttle on enrollment — anonymous, per IP."""
    scope = "enroll"


class LoginThrottle(AnonRateThrottle):
    scope = "login"


class AgentThrottle(SimpleRateThrottle):
    """Per-agent throttle: keyed on the authenticated agent's id."""
    scope = "agent"

    def get_cache_key(self, request, view):
        from apps.agents.models import Agent
        agent = request.auth
        if not isinstance(agent, Agent):
            return None
        return f"throttle_agent_{agent.id}"


__all__ = [
    "BurstAnonThrottle", "UserScopedThrottle",
    "EnrollThrottle", "LoginThrottle", "AgentThrottle",
]
