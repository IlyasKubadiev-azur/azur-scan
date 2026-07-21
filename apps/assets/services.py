"""Asset write-side services. All mutations go through here, not raw ORM."""
from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.assets.models import Asset, AssetOwnerHistory


@transaction.atomic
def reassign_owner(*, asset: Asset, new_owner_email: str, actor) -> Asset:
    """Set the current owner (by email string) and append a row to history."""
    now = timezone.now()
    new_owner_email = (new_owner_email or "").strip().lower()

    # Close out the previous owner record (if any)
    AssetOwnerHistory.objects.filter(
        asset=asset, unassigned_at__isnull=True,
    ).update(unassigned_at=now)

    asset.current_owner_email = new_owner_email
    asset.save(update_fields=["current_owner_email", "updated_at"])

    if new_owner_email:
        AssetOwnerHistory.objects.create(
            asset=asset,
            owner_email=new_owner_email,
            assigned_at=now,
            assigned_by=actor if getattr(actor, "is_authenticated", False) else None,
        )
    return asset


@transaction.atomic
def create_manual_asset(
    *, hostname: str, asset_type=None, owner_email: str = "", notes: str = "",
) -> Asset:
    owner_email = (owner_email or "").strip().lower()
    asset = Asset.objects.create(
        hostname=hostname,
        asset_type=asset_type,
        current_owner_email=owner_email,
        notes=notes,
        is_manual=True,
        status=Asset.Status.UNKNOWN,
    )
    if owner_email:
        AssetOwnerHistory.objects.create(
            asset=asset, owner_email=owner_email, assigned_at=timezone.now(),
        )
    return asset
