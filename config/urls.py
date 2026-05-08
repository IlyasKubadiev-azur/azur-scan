import platform
import time

from django.contrib import admin
from django.db import connection
from django.http import JsonResponse
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.core.views import landing

_START_TIME = time.time()


def healthz(_request):
    checks = {}

    # Database
    try:
        connection.ensure_connection()
        with connection.cursor() as cur:
            cur.execute("SELECT 1")
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {exc}"

    # Redis / cache
    try:
        from django.core.cache import cache
        cache.set("_healthz", "1", timeout=5)
        assert cache.get("_healthz") == "1"
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"error: {exc}"

    # Stats (best-effort — don't let DB errors here affect status)
    stats: dict = {}
    try:
        from apps.agents.models import Agent, AgentCommand
        from apps.assets.models import Asset
        from apps.scanning.models import ScanSession
        from django.utils import timezone
        from datetime import timedelta

        now = timezone.now()
        stats = {
            "assets_total": Asset.objects.count(),
            "assets_online": Asset.objects.filter(status="online").count(),
            "agents_active": Agent.objects.filter(is_revoked=False).count(),
            "commands_pending": AgentCommand.objects.filter(status="queued").count(),
            "scans_last_24h": ScanSession.objects.filter(
                received_at__gte=now - timedelta(hours=24)
            ).count(),
        }
    except Exception:
        pass

    overall = "ok" if all(v == "ok" for v in checks.values()) else "degraded"
    payload = {
        "status": overall,
        "uptime_seconds": int(time.time() - _START_TIME),
        "python": platform.python_version(),
        "checks": checks,
        "stats": stats,
    }
    return JsonResponse(payload, status=200 if overall == "ok" else 503)


urlpatterns = [
    path("", landing, name="landing"),
    path("admin/", admin.site.urls),
    # Django built-in i18n: provides POST /i18n/setlang/ for language switching.
    path("i18n/", include("django.conf.urls.i18n")),
    path("api/v1/", include(("apps.api.v1.urls", "api_v1"), namespace="v1")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger"),
    path("healthz", healthz, name="healthz"),
]
