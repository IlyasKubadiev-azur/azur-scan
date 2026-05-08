from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from apps.assets.models import (
    Asset, AssetOwnerHistory, AssetType, Disk, NetworkInterface,
)


@admin.register(AssetType)
class AssetTypeAdmin(ModelAdmin):
    list_display = ("code", "label")
    search_fields = ("code", "label")


class NetworkInterfaceInline(TabularInline):
    model = NetworkInterface
    extra = 0
    readonly_fields = ("name", "mac_address", "ip_addresses", "is_primary", "updated_at")
    can_delete = False


class DiskInline(TabularInline):
    model = Disk
    extra = 0
    readonly_fields = ("device", "model", "size_bytes", "free_bytes", "fs_type", "mount_point", "updated_at")
    can_delete = False


@admin.register(Asset)
class AssetAdmin(ModelAdmin):
    list_display = (
        "hostname", "serial_number", "manufacturer", "model", "os_name",
        "current_user_login", "current_owner", "status", "last_seen_at",
    )
    list_display_links = ("hostname", "serial_number")
    list_filter = ("status", "asset_type", "os_name", "is_manual")
    search_fields = ("hostname", "fqdn", "serial_number", "manufacturer", "model")
    readonly_fields = (
        "id", "first_seen_at", "last_seen_at", "agent_version",
        "current_user_login", "last_logged_user",
        "os_name", "os_version", "os_build", "os_arch",
        "cpu_model", "cpu_cores", "ram_total_mb", "motherboard", "gpu",
        "manufacturer", "model", "serial_number",
        "created_at", "updated_at",
    )
    fieldsets = (
        ("Identity", {
            "fields": ("id", "hostname", "fqdn", "asset_type", "is_manual"),
        }),
        ("Hardware (auto-collected)", {
            "fields": (
                "manufacturer", "model", "serial_number",
                "cpu_model", "cpu_cores", "ram_total_mb", "motherboard", "gpu",
            ),
        }),
        ("OS (auto-collected)", {
            "fields": ("os_name", "os_version", "os_build", "os_arch"),
        }),
        ("Users / ownership", {
            "fields": ("current_user_login", "last_logged_user", "current_owner"),
        }),
        ("Service", {
            "fields": ("status", "first_seen_at", "last_seen_at", "agent_version"),
        }),
        ("Notes", {"fields": ("notes",)}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )
    inlines = [NetworkInterfaceInline, DiskInline]
    autocomplete_fields = ("current_owner", "asset_type")


@admin.register(AssetOwnerHistory)
class AssetOwnerHistoryAdmin(ModelAdmin):
    list_display = ("asset", "user", "assigned_at", "unassigned_at", "assigned_by")
    autocomplete_fields = ("asset", "user", "assigned_by")
