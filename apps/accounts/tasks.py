"""Periodic accounts tasks (Celery)."""
from __future__ import annotations

import logging
from io import StringIO

from celery import shared_task
from django.conf import settings
from django.core.management import call_command

log = logging.getLogger(__name__)


@shared_task(
    name="accounts.sync_ldap_users",
    ignore_result=True,
    autoretry_for=(Exception,),
    retry_backoff=60,
    retry_backoff_max=600,
    max_retries=3,
)
def sync_ldap_users_task() -> str:
    """Schedule via django-celery-beat (default: every 15 minutes).

    Returns the stdout of the management command (also written to logs)
    so beat history is debuggable from the admin.
    """
    if not getattr(settings, "LDAP_ENABLED", False):
        log.info("LDAP_ENABLED=False — skipping sync")
        return "skipped: LDAP_ENABLED=False"

    buf = StringIO()
    try:
        call_command("sync_ldap_users", stdout=buf, stderr=buf)
    except Exception as exc:
        log.exception("sync_ldap_users failed")
        raise

    output = buf.getvalue().strip()
    log.info("sync_ldap_users result:\n%s", output)
    return output
