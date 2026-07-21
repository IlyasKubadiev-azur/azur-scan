from django.db import models

from apps.core.models import TimeStampedModel, UUIDPKModel


class AssetType(models.Model):
    code = models.CharField(max_length=32, unique=True)
    label = models.CharField(max_length=64)

    class Meta:
        db_table = "assets_asset_type"
        ordering = ["label"]

    def __str__(self) -> str:
        return self.label


class Asset(UUIDPKModel, TimeStampedModel):
    class Status(models.TextChoices):
        ONLINE = "online", "Online"
        OFFLINE = "offline", "Offline"
        UNKNOWN = "unknown", "Unknown"

    # Identity
    hostname = models.CharField(max_length=255, db_index=True)
    fqdn = models.CharField(max_length=512, blank=True, default="")
    serial_number = models.CharField(max_length=128, blank=True, default="")
    manufacturer = models.CharField(max_length=128, blank=True, default="")
    model = models.CharField(max_length=128, blank=True, default="")
    asset_type = models.ForeignKey(
        AssetType, on_delete=models.PROTECT,
        null=True, blank=True, related_name="assets",
    )

    # OS
    os_name = models.CharField(max_length=64, blank=True, default="")
    os_version = models.CharField(max_length=64, blank=True, default="")
    os_build = models.CharField(max_length=64, blank=True, default="")
    os_arch = models.CharField(max_length=32, blank=True, default="")
    # Display version: Windows feature update like "24H2", "25H2";
    # macOS friendly name like "Sonoma 14.5"
    os_display_version = models.CharField(max_length=32, blank=True, default="")
    os_edition = models.CharField(max_length=64, blank=True, default="")  # Pro / Enterprise / Home

    # Hardware (denormalized hot fields; full snapshot lives in ScanSession.payload)
    cpu_model = models.CharField(max_length=255, blank=True, default="")
    cpu_vendor = models.CharField(max_length=32, blank=True, default="")     # Intel / AMD / Apple
    cpu_cores = models.PositiveSmallIntegerField(null=True, blank=True)
    cpu_threads = models.PositiveSmallIntegerField(null=True, blank=True)
    cpu_base_ghz = models.DecimalField(
        max_digits=4, decimal_places=2, null=True, blank=True,
    )
    cpu_arch = models.CharField(max_length=32, blank=True, default="")       # x86_64 / arm64
    ram_total_mb = models.PositiveIntegerField(null=True, blank=True)

    # Motherboard split into manufacturer / product / serial.
    # `motherboard` kept for backward compat ("Manufacturer Product" composite).
    motherboard = models.CharField(max_length=255, blank=True, default="")
    motherboard_manufacturer = models.CharField(max_length=128, blank=True, default="")
    motherboard_product = models.CharField(max_length=128, blank=True, default="")
    motherboard_serial = models.CharField(max_length=128, blank=True, default="")

    # BIOS / UEFI firmware
    bios_vendor = models.CharField(max_length=128, blank=True, default="")
    bios_version = models.CharField(max_length=64, blank=True, default="")
    bios_release_date = models.CharField(max_length=32, blank=True, default="")

    gpu = models.CharField(max_length=255, blank=True, default="")

    # Users
    current_user_login = models.CharField(max_length=128, blank=True, default="")
    last_logged_user = models.CharField(max_length=128, blank=True, default="")
    # Free-form email — operator types who owns this device. Not tied to any
    # user account: we removed the AD/LDAP integration since it was more
    # ceremony than value for this workflow.
    current_owner_email = models.EmailField(blank=True, default="", db_index=True)

    # Service metadata
    status = models.CharField(
        max_length=16, choices=Status.choices,
        default=Status.UNKNOWN, db_index=True,
    )
    first_seen_at = models.DateTimeField(null=True, blank=True)
    last_seen_at = models.DateTimeField(null=True, blank=True, db_index=True)
    agent_version = models.CharField(max_length=32, blank=True, default="")
    is_manual = models.BooleanField(default=False)

    notes = models.TextField(blank=True, default="")

    class Meta:
        db_table = "assets_asset"
        ordering = ["-last_seen_at", "hostname"]
        constraints = [
            models.UniqueConstraint(
                fields=["serial_number"],
                condition=~models.Q(serial_number=""),
                name="uniq_asset_serial_when_present",
            ),
        ]
        indexes = [
            models.Index(fields=["hostname"], name="asset_hostname_idx"),
            models.Index(fields=["-last_seen_at"], name="asset_last_seen_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.hostname} ({self.serial_number or 'no-serial'})"


class AssetOwnerHistory(TimeStampedModel):
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="owner_history")
    owner_email = models.EmailField(blank=True, default="")
    assigned_at = models.DateTimeField()
    unassigned_at = models.DateTimeField(null=True, blank=True)
    assigned_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )

    class Meta:
        db_table = "assets_owner_history"
        ordering = ["-assigned_at"]


class NetworkInterface(TimeStampedModel):
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="network_interfaces")
    name = models.CharField(max_length=128)
    mac_address = models.CharField(max_length=64)
    ip_addresses = models.JSONField(default=list, blank=True)  # list[str]
    is_primary = models.BooleanField(default=False)

    class Meta:
        db_table = "assets_nic"
        constraints = [
            models.UniqueConstraint(fields=["asset", "mac_address"], name="uniq_asset_mac"),
        ]


class Disk(TimeStampedModel):
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="disks")
    device = models.CharField(max_length=128)
    model = models.CharField(max_length=255, blank=True, default="")
    size_bytes = models.BigIntegerField(null=True, blank=True)
    free_bytes = models.BigIntegerField(null=True, blank=True)
    fs_type = models.CharField(max_length=32, blank=True, default="")
    mount_point = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        db_table = "assets_disk"
