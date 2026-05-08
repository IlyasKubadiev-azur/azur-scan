from django.contrib import admin
from unfold.admin import ModelAdmin

from apps.core.models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(ModelAdmin):
    list_display = ("created_at", "actor", "action", "object_type", "object_id", "ip")
    list_filter = ("action", "object_type")
    search_fields = ("object_id", "actor__username", "ip", "action")
    readonly_fields = [f.name for f in AuditLog._meta.get_fields() if not f.is_relation or f.many_to_one]
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
