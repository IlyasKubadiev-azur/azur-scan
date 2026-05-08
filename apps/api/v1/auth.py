"""User authentication endpoints + minimal user list for the admin UI."""
from rest_framework import serializers, viewsets
from rest_framework.permissions import IsAdminUser
from rest_framework_simplejwt.views import (
    TokenBlacklistView, TokenObtainPairView, TokenRefreshView,
)

from apps.accounts.models import User


class UserSerializer(serializers.ModelSerializer):
    roles = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id", "username", "email", "first_name", "last_name",
            "is_active", "is_staff", "is_superuser", "roles",
        ]

    def get_roles(self, obj: User) -> list[str]:
        return list(obj.user_roles.values_list("role__code", flat=True))


class UserViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = User.objects.all().prefetch_related("user_roles__role")
    serializer_class = UserSerializer
    permission_classes = [IsAdminUser]
    search_fields = ["username", "email", "first_name", "last_name"]


login_view = TokenObtainPairView.as_view()
refresh_view = TokenRefreshView.as_view()
logout_view = TokenBlacklistView.as_view()
