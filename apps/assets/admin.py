from django.contrib import admin, messages
from django.shortcuts import redirect
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import action

from apps.agents.services import issue_rescan_command
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
        "hostname", "serial_number", "manufacturer", "model",
        "os_display", "cpu_model", "current_owner", "status", "last_seen_at",
    )
    list_display_links = ("hostname", "serial_number")
    list_filter = ("status", "asset_type", "os_name", "cpu_vendor", "is_manual")
    search_fields = (
        "hostname", "fqdn", "serial_number", "manufacturer", "model",
        "cpu_model", "bios_version",
    )
    readonly_fields = (
        "id", "first_seen_at", "last_seen_at", "agent_version",
        "current_user_login", "last_logged_user",
        "os_name", "os_version", "os_build", "os_arch",
        "os_display_version", "os_edition",
        "cpu_model", "cpu_vendor", "cpu_cores", "cpu_threads",
        "cpu_base_ghz", "cpu_arch",
        "ram_total_mb",
        "motherboard", "motherboard_manufacturer", "motherboard_product",
        "motherboard_serial",
        "bios_vendor", "bios_version", "bios_release_date",
        "gpu",
        "manufacturer", "model", "serial_number",
        "created_at", "updated_at",
    )
    fieldsets = (
        ("Identity", {
            "fields": ("id", "hostname", "fqdn", "asset_type", "is_manual"),
        }),
        ("OS (auto-collected)", {
            "fields": (
                "os_name", "os_display_version", "os_edition",
                "os_version", "os_build", "os_arch",
            ),
        }),
        ("CPU (auto-collected)", {
            "fields": (
                "cpu_model", "cpu_vendor",
                ("cpu_cores", "cpu_threads"),
                ("cpu_base_ghz", "cpu_arch"),
            ),
        }),
        ("Memory & GPU (auto-collected)", {
            "fields": ("ram_total_mb", "gpu"),
        }),
        ("Motherboard (auto-collected)", {
            "fields": (
                "motherboard_manufacturer", "motherboard_product",
                "motherboard_serial", "motherboard",
            ),
        }),
        ("BIOS / firmware (auto-collected)", {
            "fields": ("bios_vendor", "bios_version", "bios_release_date"),
        }),
        ("Chassis (auto-collected)", {
            "fields": ("manufacturer", "model", "serial_number"),
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

    # django-unfold detail-page action: renders as a button at the top of the
    # Asset edit page. Visible only on saved objects (not on the "Add" form).
    actions_detail = ["rescan_now"]

    @admin.display(description="OS", ordering="os_name")
    def os_display(self, obj):
        """Compact OS column for list view: 'Windows 11 25H2 Pro'."""
        parts = [obj.os_name, obj.os_version]
        if obj.os_display_version:
            parts.append(obj.os_display_version)
        if obj.os_edition and obj.os_edition.lower() not in (obj.os_name or "").lower():
            parts.append(obj.os_edition)
        return " ".join(p for p in parts if p) or "—"

    @action(
        description="Run scan now",
        url_path="rescan-now",
        icon="radar",
    )
    def rescan_now(self, request, object_id: str):
        """Queue an immediate rescan command for this asset's agent.

        Routed at /admin/assets/asset/<pk>/rescan-now/. The action button is
        rendered by django-unfold on the detail page (top toolbar).
        """
        asset = self.get_object(request, object_id)
        if asset is None:
            messages.error(request, "Asset not found.")
            return redirect("admin:assets_asset_changelist")

        agent = getattr(asset, "agent", None)
        if agent is None:
            messages.warning(
                request,
                f"{asset.hostname}: no enrolled agent on this device, nothing to rescan.",
            )
        elif agent.is_revoked:
            messages.warning(
                request,
                f"{asset.hostname}: agent is revoked — re-enroll required before rescan.",
            )
        else:
            cmd = issue_rescan_command(agent=agent, requested_by=request.user)
            messages.success(
                request,
                f"{asset.hostname}: rescan queued (command {cmd.id}). "
                f"The agent will pick it up on the next heartbeat "
                f"(within ~{agent.asset.agent_version and 90 or 90}s).",
            )
        return redirect(
            "admin:assets_asset_change", object_id=str(asset.id),
        )


@admin.register(AssetOwnerHistory)
class AssetOwnerHistoryAdmin(ModelAdmin):
    list_display = ("asset", "user", "assigned_at", "unassigned_at", "assigned_by")
    autocomplete_fields = ("asset", "user", "assigned_by")
