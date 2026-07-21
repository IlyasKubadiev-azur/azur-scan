"""Asset write-side services. All mutations go through here, not raw ORM."""
from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.assets.models import Asset, AssetOwnerHistory
from apps.core import audit


@transaction.atomic
def reassign_owner(*, asset: Asset, new_owner_email: str, actor) -> Asset:
    """Set the current owner (by email string) and append a row to history."""
    now = timezone.now()
    new_owner_email = (new_owner_email or "").strip().lower()
    old_owner_email = asset.current_owner_email

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

    if old_owner_email != new_owner_email:
        audit.log_event(
            action=audit.ASSET_OWNER_CHANGED,
            actor=actor,
            object_type="asset",
            object_id=asset.id,
            before={"owner_email": old_owner_email},
            after={"owner_email": new_owner_email, "hostname": asset.hostname},
        )
    return asset


@transaction.atomic
def create_manual_asset(
    *, hostname: str, asset_type=None, owner_email: str = "", notes: str = "",
    actor=None,
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
    audit.log_event(
        action=audit.ASSET_MANUAL_CREATED,
        actor=actor,
        object_type="asset",
        object_id=asset.id,
        after={
            "hostname": hostname,
            "owner_email": owner_email,
            "asset_type": getattr(asset_type, "code", None),
        },
    )
    return asset
