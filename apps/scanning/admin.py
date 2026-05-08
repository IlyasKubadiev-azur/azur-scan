from django.contrib import admin
from unfold.admin import ModelAdmin

from apps.scanning.models import ScanSession


@admin.register(ScanSession)
class ScanSessionAdmin(ModelAdmin):
    list_display = (
        "id", "asset", "agent", "source",
        "agent_version", "started_at", "finished_at", "received_at",
    )
    list_filter = ("source",)
    search_fields = ("asset__hostname", "client_scan_id", "id")
    # `agent` is intentionally NOT in autocomplete_fields — Agent model is
    # not registered in the admin (hidden from web UI). The FK still renders
    # as a read-only label here.
    autocomplete_fields = ("asset",)
    readonly_fields = [
        f.name for f in ScanSession._meta.get_fields()
        if not f.is_relation or f.many_to_one
    ]
    date_hierarchy = "received_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
