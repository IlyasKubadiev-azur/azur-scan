from rest_framework import serializers

from apps.agents.models import Agent


class FingerprintSerializer(serializers.Serializer):
    machine_id = serializers.CharField(max_length=128)
    primary_mac = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    hostname = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    os_kind = serializers.ChoiceField(choices=[c[0] for c in Agent.OSKind.choices])
    agent_version = serializers.CharField(max_length=32)
    public_key_fingerprint = serializers.CharField(required=False, allow_blank=True, default="")


class EnrollmentRequestSerializer(serializers.Serializer):
    fingerprint = FingerprintSerializer()


class EnrollmentResponseSerializer(serializers.Serializer):
    device_id = serializers.UUIDField()
    access_token = serializers.CharField()
    refresh_token = serializers.CharField()
    config = serializers.DictField()


class HeartbeatRequestSerializer(serializers.Serializer):
    uptime_s = serializers.IntegerField(required=False, default=0, min_value=0)
    last_scan_at = serializers.DateTimeField(required=False, allow_null=True)
    agent_version = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")


class CommandSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    type = serializers.CharField()
    params = serializers.DictField()


class HeartbeatResponseSerializer(serializers.Serializer):
    now = serializers.DateTimeField()
    commands = CommandSerializer(many=True)


class ScanUploadSerializer(serializers.Serializer):
    """Light DRF validation. Strict validation happens in pydantic schemas."""

    scan_id = serializers.CharField(max_length=64)
    started_at = serializers.DateTimeField()
    finished_at = serializers.DateTimeField()
    source = serializers.CharField(required=False, default="scheduled")
    agent_version = serializers.CharField(max_length=32)
    system = serializers.DictField()
    os = serializers.DictField(required=False, default=dict)
    hardware = serializers.DictField(required=False, default=dict)
    storage = serializers.DictField(required=False, default=dict)
    network = serializers.DictField(required=False, default=dict)
    errors = serializers.DictField(required=False, default=dict)


class CommandAckRequestSerializer(serializers.Serializer):
    result = serializers.DictField(required=False, default=dict)


class TokenRefreshRequestSerializer(serializers.Serializer):
    refresh_token = serializers.CharField()


class TokenRefreshResponseSerializer(serializers.Serializer):
    access_token = serializers.CharField()
