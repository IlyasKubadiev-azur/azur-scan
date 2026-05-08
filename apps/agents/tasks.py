from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.agents.models import AgentCommand
from apps.assets.models import Asset


@shared_task
def mark_offline_assets() -> int:
    """Flip assets to OFFLINE if their agent hasn't heartbeated for too long."""
    cutoff = timezone.now() - settings.AGENT_OFFLINE_AFTER
    updated = (
        Asset.objects
        .filter(agent__last_heartbeat_at__lt=cutoff)
        .exclude(status=Asset.Status.OFFLINE)
        .update(status=Asset.Status.OFFLINE)
    )
    return updated


@shared_task
def expire_old_commands() -> int:
    """Mark queued commands past their expires_at as EXPIRED."""
    return AgentCommand.objects.filter(
        status=AgentCommand.Status.QUEUED,
        expires_at__lt=timezone.now(),
    ).update(status=AgentCommand.Status.EXPIRED)
