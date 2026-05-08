from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel, UUIDPKModel


class Agent(UUIDPKModel, TimeStampedModel):
    class OSKind(models.TextChoices):
        WINDOWS = "windows", "Windows"
        MACOS = "macos", "macOS"
        LINUX = "linux", "Linux"

    asset = models.OneToOneField(
        "assets.Asset", on_delete=models.CASCADE, related_name="agent",
    )
    machine_id = models.CharField(max_length=128, db_index=True, unique=True)
    public_key_fingerprint = models.CharField(max_length=128, blank=True, default="")

    # JTI of the currently valid access / refresh JWT. Empty = revoked / not yet issued.
    jwt_jti = models.CharField(max_length=64, blank=True, default="", db_index=True)
    refresh_jti = models.CharField(max_length=64, blank=True, default="", db_index=True)

    enrolled_at = models.DateTimeField(default=timezone.now)
    last_heartbeat_at = models.DateTimeField(null=True, blank=True, db_index=True)
    agent_version = models.CharField(max_length=32, blank=True, default="")
    os_kind = models.CharField(max_length=16, choices=OSKind.choices)

    is_revoked = models.BooleanField(default=False)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_reason = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        db_table = "agents_agent"

    def __str__(self) -> str:
        return f"Agent({self.asset.hostname})"


class AgentCommand(UUIDPKModel, TimeStampedModel):
    class Type(models.TextChoices):
        RESCAN = "rescan", "Rescan"
        UPDATE_CONFIG = "update_config", "Update config"
        REVOKE = "revoke", "Revoke"

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        DISPATCHED = "dispatched", "Dispatched"
        ACKED = "acked", "Acknowledged"
        FAILED = "failed", "Failed"
        EXPIRED = "expired", "Expired"

    agent = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name="commands")
    type = models.CharField(max_length=32, choices=Type.choices)
    params = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=16, choices=Status.choices,
        default=Status.QUEUED, db_index=True,
    )
    dispatched_at = models.DateTimeField(null=True, blank=True)
    acked_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField()
    result = models.JSONField(null=True, blank=True)
    created_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )

    class Meta:
        db_table = "agents_command"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["agent", "status"], name="cmd_agent_status_idx"),
        ]
