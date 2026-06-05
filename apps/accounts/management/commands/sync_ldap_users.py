"""Pull all users from Active Directory into the Django User table.

Runs even for users who have never logged in, so the Asset "Current owner"
dropdown is populated with the full domain directory.

Configuration: see config/settings/base.py — needs LDAP_ENABLED=True plus
AUTH_LDAP_* env vars (server URI, bind DN, password, search base).

Usage:
    docker compose exec web python manage.py sync_ldap_users
    docker compose exec web python manage.py sync_ldap_users --dry-run
    docker compose exec web python manage.py sync_ldap_users --filter "(memberOf=...)"

Triggered automatically on a 15-minute schedule via Celery beat
(see apps.accounts.tasks.sync_ldap_users_task).
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

log = logging.getLogger(__name__)


# AD attribute → User field map. Override via env if your schema differs.
DEFAULT_ATTR_MAP = {
    "sAMAccountName": "username",
    "userPrincipalName": "username_alt",  # fallback if sAMAccountName empty
    "mail": "email",
    "givenName": "first_name",
    "sn": "last_name",
    "distinguishedName": "ldap_dn",
    "objectGUID": "ldap_object_guid",
    "userAccountControl": "_uac",  # bit 0x2 = ACCOUNTDISABLE
}

ATTRS_REQUESTED = [
    "sAMAccountName", "userPrincipalName", "mail",
    "givenName", "sn", "distinguishedName",
    "objectGUID", "userAccountControl",
]

# Default LDAP filter: enabled user accounts, not computers/contacts.
# (&(objectClass=user)(objectCategory=person)(!(userAccountControl:1.2.840.113556.1.4.803:=2)))
DEFAULT_FILTER = (
    "(&(objectClass=user)"
    "(objectCategory=person)"
    "(!(userAccountControl:1.2.840.113556.1.4.803:=2)))"
)


class Command(BaseCommand):
    help = "Synchronize Django User table from Active Directory"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Don't write to DB; just print what would happen.",
        )
        parser.add_argument(
            "--filter", default=DEFAULT_FILTER,
            help="LDAP search filter (default: enabled person accounts only).",
        )
        parser.add_argument(
            "--page-size", type=int, default=500,
            help="LDAP paged search page size (default 500).",
        )

    def handle(self, *args, **opts):
        if not getattr(settings, "LDAP_ENABLED", False):
            raise CommandError(
                "LDAP_ENABLED is False. Set it in .env and restart the web "
                "container to enable directory sync."
            )

        try:
            import ldap
            from ldap.controls import SimplePagedResultsControl
        except ImportError as exc:
            raise CommandError(
                "python-ldap is not installed. It should come with "
                "django-auth-ldap — check `pip list`."
            ) from exc

        uri = settings.AUTH_LDAP_SERVER_URI
        bind_dn = settings.AUTH_LDAP_BIND_DN
        bind_pw = settings.AUTH_LDAP_BIND_PASSWORD
        search_base = settings.AUTH_LDAP_USER_SEARCH.base_dn

        self.stdout.write(f"Connecting to {uri}...")
        conn = ldap.initialize(uri)
        conn.set_option(ldap.OPT_REFERRALS, 0)
        conn.set_option(ldap.OPT_PROTOCOL_VERSION, 3)
        # If using ldaps:// with self-signed cert, tighten in production.
        conn.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_ALLOW)

        try:
            conn.simple_bind_s(bind_dn, bind_pw)
        except ldap.INVALID_CREDENTIALS as exc:
            raise CommandError(f"LDAP bind failed: invalid credentials ({exc})")
        except ldap.LDAPError as exc:
            raise CommandError(f"LDAP bind failed: {exc}")

        self.stdout.write(f"Bound as {bind_dn}. Searching {search_base}...")

        page_control = SimplePagedResultsControl(
            criticality=True, size=opts["page_size"], cookie="",
        )

        seen_usernames: set[str] = set()
        created = updated = disabled = 0

        try:
            while True:
                msgid = conn.search_ext(
                    search_base,
                    ldap.SCOPE_SUBTREE,
                    opts["filter"],
                    ATTRS_REQUESTED,
                    serverctrls=[page_control],
                )
                _rtype, rdata, _rmsgid, sctrls = conn.result3(msgid)

                for dn, entry in rdata:
                    if not dn:
                        continue
                    c, u, d = self._upsert_user(entry, dry_run=opts["dry_run"])
                    created += c
                    updated += u
                    disabled += d
                    uname = _first(entry.get("sAMAccountName")) \
                        or _first(entry.get("userPrincipalName")) or ""
                    if uname:
                        seen_usernames.add(uname.lower())

                # Pagination
                cookie = b""
                for ctrl in sctrls:
                    if ctrl.controlType == SimplePagedResultsControl.controlType:
                        cookie = ctrl.cookie
                if not cookie:
                    break
                page_control.cookie = cookie
        finally:
            try:
                conn.unbind_s()
            except Exception:
                pass

        # Soft-deactivate Django users that have ldap_dn set but were not seen
        # in this sync (deleted/disabled in AD). NEVER deactivate local-only
        # accounts (no ldap_dn) — those are dev superusers and similar.
        deactivated = self._deactivate_missing(seen_usernames, dry_run=opts["dry_run"])

        self.stdout.write(self.style.SUCCESS(
            f"Sync complete: {created} created, {updated} updated, "
            f"{disabled} disabled (in AD), {deactivated} deactivated "
            f"(missing from AD)."
        ))

    # ------------------------------------------------------------------
    # Per-user upsert
    # ------------------------------------------------------------------

    @transaction.atomic
    def _upsert_user(self, entry: dict, *, dry_run: bool) -> tuple[int, int, int]:
        from apps.accounts.models import User

        username = _first(entry.get("sAMAccountName"))
        if not username:
            upn = _first(entry.get("userPrincipalName"))
            if upn and "@" in upn:
                username = upn.split("@", 1)[0]
        if not username:
            return (0, 0, 0)

        uac_raw = _first(entry.get("userAccountControl"))
        try:
            uac = int(uac_raw) if uac_raw else 0
        except ValueError:
            uac = 0
        is_disabled = bool(uac & 0x2)

        fields = {
            "email": _first(entry.get("mail")) or "",
            "first_name": _first(entry.get("givenName")) or "",
            "last_name": _first(entry.get("sn")) or "",
            "ldap_dn": _first(entry.get("distinguishedName")) or "",
            "is_active": not is_disabled,
        }

        if dry_run:
            self.stdout.write(f"  [dry-run] {username:30s}  {fields['email']:35s}")
            return (0, 0, 0)

        obj, created = User.objects.get_or_create(
            username=username, defaults=fields,
        )
        if created:
            obj.set_unusable_password()  # only LDAP auth, no Django password
            obj.save()
            return (1, 0, 1 if is_disabled else 0)

        # Update only if something changed
        changed = False
        for k, v in fields.items():
            if getattr(obj, k) != v:
                setattr(obj, k, v)
                changed = True
        if changed:
            obj.save()
            return (0, 1, 1 if is_disabled else 0)
        return (0, 0, 1 if is_disabled else 0)

    # ------------------------------------------------------------------
    # Soft-deactivate users no longer present in AD
    # ------------------------------------------------------------------

    def _deactivate_missing(self, seen: set[str], *, dry_run: bool) -> int:
        from apps.accounts.models import User
        qs = User.objects.exclude(ldap_dn="").filter(is_active=True)
        count = 0
        for u in qs:
            if u.username.lower() not in seen:
                if dry_run:
                    self.stdout.write(f"  [dry-run] DEACTIVATE missing: {u.username}")
                else:
                    u.is_active = False
                    u.save(update_fields=["is_active"])
                count += 1
        return count


def _first(val):
    """LDAP returns lists of bytes. Decode the first entry to str."""
    if not val:
        return ""
    item = val[0] if isinstance(val, list) else val
    if isinstance(item, bytes):
        try:
            return item.decode("utf-8")
        except UnicodeDecodeError:
            return item.decode("latin-1", errors="replace")
    return str(item)
