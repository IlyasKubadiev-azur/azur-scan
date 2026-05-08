from rest_framework.permissions import BasePermission

from apps.agents.models import Agent


class IsAgent(BasePermission):
    """Allow only requests authenticated by `AgentJWTAuthentication`."""

    message = "agent_authentication_required"

    def has_permission(self, request, view) -> bool:
        return isinstance(request.auth, Agent) and not request.auth.is_revoked
