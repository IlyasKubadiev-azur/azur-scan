"""Signal handlers that funnel Django events into core.AuditLog.

Registered in CoreConfig.ready(). Keep this file cheap on import — anything
heavy would run on every worker startup.
"""
from __future__ import annotations

from django.contrib.auth.signals import (
    user_logged_in, user_logged_out, user_login_failed,
)
from django.db.models.signals import post_delete
from django.dispatch import receiver

from apps.core import audit


@receiver(user_logged_in)
def _on_login(sender, request, user, **kwargs):
    audit.log_event(
        action=audit.USER_LOGGED_IN,
        actor=user,
        object_type="user",
        object_id=user.pk,
        request=request,
    )


@receiver(user_logged_out)
def _on_logout(sender, request, user, **kwargs):
    if user is None:
        return  # anonymous "logout" — Django fires this for AnonymousUser too
    audit.log_event(
        action=audit.USER_LOGGED_OUT,
        actor=user,
        object_type="user",
        object_id=user.pk,
        request=request,
    )


@receiver(user_login_failed)
def _on_login_failed(sender, credentials, request, **kwargs):
    # Never store the password — only the username attempt
    audit.log_event(
        action=audit.USER_LOGIN_FAILED,
        object_type="user",
        object_id=credentials.get("username") or "",
        request=request,
        after={"attempted_username": credentials.get("username")},
    )


def _register_asset_delete_signal():
    """Wire up post_delete on Asset. Deferred so accounts/assets apps are ready."""
    from apps.assets.models import Asset

    @receiver(post_delete, sender=Asset, weak=False)
    def _on_asset_delete(sender, instance, **kwargs):
        audit.log_event(
            action=audit.ASSET_DELETED,
            object_type="asset",
            object_id=instance.id,
            before={
                "hostname": instance.hostname,
                "serial_number": instance.serial_number,
                "owner_email": instance.current_owner_email,
                "manufacturer": instance.manufacturer,
                "model": instance.model,
            },
        )
