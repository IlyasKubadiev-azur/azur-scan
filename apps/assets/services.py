"""Asset write-side services. All mutations go through here, not raw ORM."""
from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.assets.models import Asset, AssetOwnerHistory


@transaction.atomic
def reassign_owner(*, asset: Asset, new_owner, actor) -> Asset:
    """Set/replace the current owner and append a row to the history."""
    now = timezone.now()

    # Close out the previous owner record (if any)
    AssetOwnerHistory.objects.filter(
        asset=asset, unassigned_at__isnull=True,
    ).update(unassigned_at=now)

    asset.current_owner = new_owner
    asset.save(update_fields=["current_owner", "updated_at"])

    if new_owner is not None:
        AssetOwnerHistory.objects.create(
            asset=asset,
            user=new_owner,
            assigned_at=now,
            assigned_by=actor if getattr(actor, "is_authenticated", False) else None,
        )
    return asset


@transaction.atomic
def create_manual_asset(*, hostname: str, asset_type=None, owner=None, notes: str = "") -> Asset:
    asset = Asset.objects.create(
        hostname=hostname,
        asset_type=asset_type,
        current_owner=owner,
        notes=notes,
        is_manual=True,
        status=Asset.Status.UNKNOWN,
    )
    if owner is not None:
        AssetOwnerHistory.objects.create(
            asset=asset, user=owner, assigned_at=timezone.now(),
        )
    return asset
