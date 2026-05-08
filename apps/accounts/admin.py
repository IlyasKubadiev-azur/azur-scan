from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from unfold.admin import ModelAdmin, TabularInline

from apps.accounts.models import Role, User, UserRole


class UserRoleInline(TabularInline):
    model = UserRole
    fk_name = "user"
    extra = 0
    autocomplete_fields = ("role",)
    fields = ("role", "granted_at", "granted_by")
    readonly_fields = ("granted_at",)


@admin.register(User)
class UserAdmin(ModelAdmin, DjangoUserAdmin):
    inlines = [UserRoleInline]
    list_display = (
        "username", "email", "first_name", "last_name",
        "is_active", "is_staff", "is_superuser", "last_login",
    )
    list_filter = ("is_active", "is_staff", "is_superuser")
    search_fields = ("username", "email", "first_name", "last_name", "ldap_dn")
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("LDAP", {"fields": ("ldap_dn", "ldap_object_guid", "last_login_ip")}),
    )


@admin.register(Role)
class RoleAdmin(ModelAdmin):
    list_display = ("code", "label")
    search_fields = ("code", "label")
