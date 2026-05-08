from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.api.v1 import agents as agents_views
from apps.api.v1 import assets as assets_views
from apps.api.v1 import auth as auth_views

router = DefaultRouter()
router.register(r"assets", assets_views.AssetViewSet, basename="assets")
router.register(r"asset-types", assets_views.AssetTypeViewSet, basename="asset-types")
router.register(r"users", auth_views.UserViewSet, basename="users")

urlpatterns = [
    # User auth
    path("auth/login", auth_views.login_view, name="auth-login"),
    path("auth/refresh", auth_views.refresh_view, name="auth-refresh"),
    path("auth/logout", auth_views.logout_view, name="auth-logout"),

    # Agent endpoints
    path("agents/enroll", agents_views.enroll, name="agent-enroll"),
    path("agents/heartbeat", agents_views.heartbeat, name="agent-heartbeat"),
    path("agents/scan", agents_views.scan, name="agent-scan"),
    path(
        "agents/commands/<uuid:command_id>/ack",
        agents_views.command_ack,
        name="agent-command-ack",
    ),
    path("agents/token/refresh", agents_views.token_refresh, name="agent-token-refresh"),

    # CRUD via DRF router
    path("", include(router.urls)),
]
