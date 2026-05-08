# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**Azur-Scan** — IT asset inventory backend (Django) + desktop agent (planned). MVP scaffolded, agent not yet started.

## Stack

- Python 3.12+, Django 5.2 LTS, DRF 3.16, SimpleJWT (users) + custom HS256 JWT (agents), pydantic 2 for scan-payload validation.
- PostgreSQL 16, Redis (cache + Celery broker), Celery + django-celery-beat.
- drf-spectacular for OpenAPI at `/api/schema/` and `/api/docs/`.
- LDAP gated behind `LDAP_ENABLED` env flag.
- Containerized via `docker-compose.yml` (postgres, redis, web=gunicorn, worker, beat).

## Common commands

```bash
# Bring up the stack (dev)
docker compose up -d --build

# Generate initial migrations (only required once after fresh checkout)
docker compose exec web python manage.py makemigrations
docker compose exec web python manage.py migrate

# Create admin user
docker compose exec web python manage.py createsuperuser

# Tail web logs
docker compose logs -f web

# Pytest
docker compose exec web pytest
```

`Makefile` wraps the common ones (`make up`, `make migrate`, `make shell`, etc).

## Architecture worth knowing

- **App layout** is HackSoft style: `models / selectors / services` per app under `apps/`. All mutations go through services; never write to the ORM from views.
- **Auth split**: `apps/agents/auth.AgentJWTAuthentication` returns `(AnonymousUser, agent)` — agent ends up in `request.auth`. Agent endpoints use `IsAgent` from `apps/agents/permissions.py`. Default `IsAuthenticated` rejects agents on purpose.
- **Two JWT secrets** in `settings.base`: `USER_JWT_SECRET` (SimpleJWT) and `AGENT_JWT_SECRET` (custom). Don't merge them.
- **Enrollment**: tokenless. Agents register by supplying only the backend URL; the backend identifies devices by stable `machine_id` (Windows MachineGuid / macOS IOPlatformUUID). Re-enrolling the same machine refreshes its JWTs in place.
- **Scan ingest** is idempotent on `(agent, client_scan_id)` — `apps/scanning/services.ingest_scan`. NIC/Disk are state (replaced each scan), `AssetOwnerHistory` is append-only.
- **Hot fields** (OS, CPU, RAM, etc.) are denormalized onto `Asset`; the full snapshot lives in `ScanSession.payload` (JSONB). Schema evolution adds fields to `apps/scanning/schemas.py` without migrations to historical scans.
- **Role hierarchy** (`apps/core/permissions.MinRole`): `viewer < operator < admin`. Views declare `min_role` or `min_role_map` (per-action). Superusers always pass.

## Settings split

`config/settings/{base,local,production,test}.py`. `DJANGO_SETTINGS_MODULE` defaults to `config.settings.local` in `manage.py` and the web Dockerfile. Production overrides cookies/HSTS/SSL redirect.

## Migrations

Only empty `__init__.py` files exist in `apps/*/migrations/`. The first task on a fresh checkout is `manage.py makemigrations` to generate them.
