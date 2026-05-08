"""Asset read-side selectors. Pure functions, no side effects."""
from __future__ import annotations

from django.db.models import QuerySet

from apps.assets.models import Asset


def list_assets() -> QuerySet[Asset]:
    return (
        Asset.objects
        .select_related("asset_type", "current_owner")
        .prefetch_related("network_interfaces", "disks")
        .order_by("-last_seen_at", "hostname")
    )


def assets_offline_for(seconds: int) -> QuerySet[Asset]:
    from datetime import timedelta
    from django.utils import timezone
    cutoff = timezone.now() - timedelta(seconds=seconds)
    return Asset.objects.filter(last_seen_at__lt=cutoff).order_by("last_seen_at")
