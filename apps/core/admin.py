import json

from django.contrib import admin
from django.utils.html import format_html
from unfold.admin import ModelAdmin

from apps.core.models import AuditLog


# Colour/emoji hints for each action prefix — makes the list view scannable.
# Groups by first dotted segment ("agent.enrolled" -> "agent").
_ACTION_LABELS = {
    "agent":   ("#3b82f6", "🛡️"),   # blue
    "scan":    ("#10b981", "📡"),   # green
    "command": ("#f59e0b", "⚡"),   # amber
    "asset":   ("#8b5cf6", "💻"),   # purple
    "user":    ("#64748b", "👤"),   # slate
}


@admin.register(AuditLog)
class AuditLogAdmin(ModelAdmin):
    list_display = (
        "created_at", "action_badge", "actor",
        "object_type", "object_short_id", "summary", "ip",
    )
    list_filter = ("action", "object_type")
    search_fields = ("object_id", "actor__username", "ip", "action",
                     "data_before", "data_after")
    readonly_fields = (
        "created_at", "updated_at", "actor", "action",
        "object_type", "object_id",
        "ip", "user_agent",
        "data_before_pretty", "data_after_pretty",
    )
    fieldsets = (
        (None, {
            "fields": ("created_at", "actor", "action",
                       "object_type", "object_id"),
        }),
        ("Request context", {
            "fields": ("ip", "user_agent"),
        }),
        ("Payload", {
            "fields": ("data_before_pretty", "data_after_pretty"),
        }),
    )
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    list_per_page = 50

    # ------------------------------------------------------------------
    # Read-only surface — audit log is append-only from the admin's POV
    # ------------------------------------------------------------------
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    # ------------------------------------------------------------------
    # Display helpers
    # ------------------------------------------------------------------

    @admin.display(description="Action", ordering="action")
    def action_badge(self, obj):
        prefix = (obj.action or "").split(".", 1)[0]
        color, icon = _ACTION_LABELS.get(prefix, ("#6b7280", "•"))
        return format_html(
            '<span style="background:{}22;color:{};padding:2px 8px;'
            'border-radius:6px;font-family:ui-monospace,monospace;'
            'font-size:12px;white-space:nowrap;">{} {}</span>',
            color, color, icon, obj.action or "-",
        )

    @admin.display(description="Object id")
    def object_short_id(self, obj):
        s = obj.object_id or ""
        return s if len(s) <= 12 else s[:8] + "…"

    @admin.display(description="Details")
    def summary(self, obj):
        """One-line highlights from data_after — what actually happened."""
        d = obj.data_after or {}
        if not d:
            return "—"
        # Cherry-pick the most useful field per action
        priority = [
            "hostname", "scan_id", "command_id", "type", "reason",
            "owner_email", "attempted_username", "agent_version",
        ]
        parts = []
        for key in priority:
            if key in d and d[key] not in ("", None):
                val = str(d[key])
                if len(val) > 40:
                    val = val[:37] + "…"
                parts.append(f"{key}={val}")
            if len(parts) >= 3:
                break
        return " · ".join(parts) if parts else "—"

    @admin.display(description="data_before")
    def data_before_pretty(self, obj):
        return _pretty_json(obj.data_before)

    @admin.display(description="data_after")
    def data_after_pretty(self, obj):
        return _pretty_json(obj.data_after)


def _pretty_json(value) -> str:
    if not value:
        return "—"
    try:
        rendered = json.dumps(value, ensure_ascii=False, indent=2)
    except (TypeError, ValueError):
        rendered = repr(value)
    return format_html(
        '<pre style="background:#0f172a;color:#e2e8f0;padding:12px;'
        'border-radius:8px;font-size:12px;line-height:1.5;'
        'max-height:400px;overflow:auto;">{}</pre>',
        rendered,
    )
