from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Extended user. Supports local auth and AD/LDAP-mirrored users."""

    ldap_dn = models.CharField(max_length=512, blank=True, default="")
    ldap_object_guid = models.UUIDField(null=True, blank=True, unique=True)
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        db_table = "accounts_user"


class Role(models.Model):
    """Application-level role. Synced from AD groups in beta+."""

    code = models.CharField(max_length=64, unique=True)
    label = models.CharField(max_length=128)
    description = models.TextField(blank=True, default="")

    class Meta:
        db_table = "accounts_role"

    def __str__(self) -> str:
        return self.label


class UserRole(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="user_roles")
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="user_roles")
    granted_at = models.DateTimeField(auto_now_add=True)
    granted_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )

    class Meta:
        db_table = "accounts_user_role"
        constraints = [
            models.UniqueConstraint(fields=["user", "role"], name="uniq_user_role"),
        ]
