"""Shared abstract models and the audit-log table."""
import uuid

from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class UUIDPKModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class AuditLog(TimeStampedModel):
    """Generic audit trail for mutating operations.

    Writes go through services explicitly — we don't auto-instrument the ORM
    because most production audit needs are at the use-case level, not row-level.
    """

    actor = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    action = models.CharField(max_length=128, db_index=True)
    object_type = models.CharField(max_length=64, db_index=True)
    object_id = models.CharField(max_length=64, db_index=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=512, blank=True, default="")
    data_before = models.JSONField(null=True, blank=True)
    data_after = models.JSONField(null=True, blank=True)

    class Meta:
        db_table = "core_audit_log"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["-created_at"], name="audit_recent_idx")]
