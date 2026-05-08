"""Helpers for django-unfold: environment label + dashboard KPI cards."""
from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.utils import timezone


def environment_callback(request) -> list[str]:
    """Render the environment badge in the admin header."""
    if settings.DEBUG:
        return ["Development", "warning"]
    return ["Production", "danger"]


def dashboard_callback(request, context: dict) -> dict:
    """Inject KPI tiles + recent activity into the admin index page.

    The Unfold default ``admin/index.html`` consumes ``kpi`` and ``progress``
    from context. We pass simple counters here.
    """
    from apps.agents.models import Agent, AgentCommand
    from apps.assets.models import Asset
    from apps.scanning.models import ScanSession

    now = timezone.now()
    last_24h = now - timedelta(hours=24)
    last_7d = now - timedelta(days=7)

    total_assets = Asset.objects.count()
    online = Asset.objects.filter(status=Asset.Status.ONLINE).count()
    offline = Asset.objects.filter(status=Asset.Status.OFFLINE).count()
    unknown = Asset.objects.filter(status=Asset.Status.UNKNOWN).count()

    agents_active = Agent.objects.filter(is_revoked=False).count()
    agents_revoked = Agent.objects.filter(is_revoked=True).count()
    pending_commands = AgentCommand.objects.filter(
        status=AgentCommand.Status.QUEUED,
    ).count()
    scans_24h = ScanSession.objects.filter(received_at__gte=last_24h).count()
    scans_7d = ScanSession.objects.filter(received_at__gte=last_7d).count()

    context.update({
        "kpi": [
            {
                "title": "Assets total",
                "metric": total_assets,
                "footer": f"{online} online · {offline} offline · {unknown} unknown",
            },
            {
                "title": "Active agents",
                "metric": agents_active,
                "footer": f"{agents_revoked} revoked",
            },
            {
                "title": "Pending commands",
                "metric": pending_commands,
                "footer": "queued, awaiting next heartbeat",
            },
            {
                "title": "Scans (24h)",
                "metric": scans_24h,
                "footer": f"{scans_7d} in last 7 days",
            },
        ],
    })
    return context
