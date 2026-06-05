from rest_framework import serializers

from apps.assets.models import Asset, AssetType, Disk, NetworkInterface
from apps.scanning.models import ScanSession


class AssetTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssetType
        fields = ["id", "code", "label"]


class NetworkInterfaceSerializer(serializers.ModelSerializer):
    class Meta:
        model = NetworkInterface
        fields = ["id", "name", "mac_address", "ip_addresses", "is_primary"]


class DiskSerializer(serializers.ModelSerializer):
    class Meta:
        model = Disk
        fields = [
            "id", "device", "model", "size_bytes",
            "free_bytes", "fs_type", "mount_point",
        ]


class AssetSerializer(serializers.ModelSerializer):
    asset_type = AssetTypeSerializer(read_only=True)
    asset_type_id = serializers.PrimaryKeyRelatedField(
        queryset=AssetType.objects.all(),
        source="asset_type",
        write_only=True,
        required=False,
        allow_null=True,
    )
    network_interfaces = NetworkInterfaceSerializer(many=True, read_only=True)
    disks = DiskSerializer(many=True, read_only=True)
    has_agent = serializers.SerializerMethodField()

    class Meta:
        model = Asset
        fields = [
            "id", "hostname", "fqdn",
            "serial_number", "manufacturer", "model",
            "asset_type", "asset_type_id",
            # OS
            "os_name", "os_version", "os_build", "os_arch",
            "os_display_version", "os_edition",
            # CPU
            "cpu_model", "cpu_vendor", "cpu_cores", "cpu_threads",
            "cpu_base_ghz", "cpu_arch",
            # Memory / GPU
            "ram_total_mb", "gpu",
            # Motherboard
            "motherboard", "motherboard_manufacturer",
            "motherboard_product", "motherboard_serial",
            # BIOS
            "bios_vendor", "bios_version", "bios_release_date",
            # Users
            "current_user_login", "last_logged_user", "current_owner",
            # Service
            "status", "first_seen_at", "last_seen_at", "agent_version",
            "is_manual", "notes",
            "network_interfaces", "disks", "has_agent",
            "created_at", "updated_at",
        ]
        # Auto-collected fields are read-only — only manual fields editable via API
        read_only_fields = [
            "id",
            "first_seen_at", "last_seen_at", "agent_version", "status",
            "os_name", "os_version", "os_build", "os_arch",
            "os_display_version", "os_edition",
            "cpu_model", "cpu_vendor", "cpu_cores", "cpu_threads",
            "cpu_base_ghz", "cpu_arch",
            "ram_total_mb", "gpu",
            "motherboard", "motherboard_manufacturer",
            "motherboard_product", "motherboard_serial",
            "bios_vendor", "bios_version", "bios_release_date",
            "manufacturer", "model", "serial_number",
            "current_user_login", "last_logged_user",
            "is_manual", "created_at", "updated_at",
        ]

    def get_has_agent(self, obj: Asset) -> bool:
        return Asset.objects.filter(pk=obj.pk, agent__isnull=False).exists()


class AssetCreateSerializer(serializers.ModelSerializer):
    """Slim serializer for manual asset creation — only the fields a human supplies."""

    asset_type_id = serializers.PrimaryKeyRelatedField(
        queryset=AssetType.objects.all(),
        source="asset_type",
        required=False,
        allow_null=True,
    )

    class Meta:
        model = Asset
        fields = ["hostname", "fqdn", "asset_type_id", "current_owner", "notes"]


class ScanSessionListSerializer(serializers.ModelSerializer):
    class Meta:
        model = ScanSession
        fields = [
            "id", "started_at", "finished_at", "received_at",
            "source", "agent_version", "payload_hash", "ingest_duration_ms",
        ]


class ScanSessionDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = ScanSession
        fields = [
            "id", "asset", "agent",
            "started_at", "finished_at", "received_at",
            "source", "agent_version", "payload_hash", "ingest_duration_ms",
            "payload", "diff_from_previous",
        ]
