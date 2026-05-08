"""Role-based permissions.

Roles form a simple hierarchy: viewer < operator < admin. Each view declares
either a `min_role` (single role for all actions) or a `min_role_map`
(per-DRF-action overrides).

Superusers always pass.
"""
from typing import Iterable

from rest_framework.permissions import BasePermission

ROLE_HIERARCHY: dict[str, int] = {
    "viewer": 1,
    "operator": 2,
    "admin": 3,
}


def _user_levels(user) -> Iterable[int]:
    codes = user.user_roles.values_list("role__code", flat=True)
    yield 0
    for code in codes:
        yield ROLE_HIERARCHY.get(code, 0)


class MinRole(BasePermission):
    """Authorize the request if user's max role-level >= required level.

    View must declare either ``min_role`` or ``min_role_map``.
    """

    def has_permission(self, request, view) -> bool:
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True

        required = self._required(view)
        if not required:
            return True

        required_level = ROLE_HIERARCHY.get(required, 999)
        return max(_user_levels(user)) >= required_level

    @staticmethod
    def _required(view) -> str | None:
        per_action = getattr(view, "min_role_map", None)
        if isinstance(per_action, dict):
            return per_action.get(getattr(view, "action", None))
        return getattr(view, "min_role", None)
