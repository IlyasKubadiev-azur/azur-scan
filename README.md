# Azur-Scan

IT asset inventory: Django backend + cross-platform agent.

## Quick start (Docker)

```bash
cp .env.example .env
# edit SECRET_KEY, USER_JWT_SECRET, AGENT_JWT_SECRET — generate with:
#   python -c "import secrets; print(secrets.token_urlsafe(64))"

docker compose up -d --build
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
```

Then:

- Django Admin: http://localhost:8000/admin/
- API root:     http://localhost:8000/api/v1/
- Swagger UI:   http://localhost:8000/api/docs/
- Health:       http://localhost:8000/healthz

## Enrolling an agent

The agent uses **tokenless** enrollment — any reachable machine can register
itself by supplying only the backend URL. Identification is by stable
`machine_id` (Windows MachineGuid / macOS IOPlatformUUID), so re-running
on the same device is idempotent.

```powershell
# After installing the MSI / setup.exe:
& "C:\Program Files\AzurScan\azurscan-agent.exe" enroll --server http://<backend-ip>:8000
```

The MSI's setup wizard does this automatically — the user just types the
backend URL once during install.

## API contract (MVP)

| Method | Path | Auth |
|---|---|---|
| POST | `/api/v1/auth/login`   | — |
| POST | `/api/v1/auth/refresh` | refresh JWT |
| POST | `/api/v1/auth/logout`  | refresh JWT |
| POST | `/api/v1/agents/enroll` | tokenless (machine_id) |
| POST | `/api/v1/agents/heartbeat` | agent JWT |
| POST | `/api/v1/agents/scan` | agent JWT |
| POST | `/api/v1/agents/commands/{id}/ack` | agent JWT |
| POST | `/api/v1/agents/token/refresh` | agent refresh JWT |
| GET / POST / PATCH / DELETE | `/api/v1/assets/...` | user JWT, role-gated |
| POST | `/api/v1/assets/{id}/rescan` | user JWT (operator+) |
| GET | `/api/v1/assets/{id}/scans` | user JWT (viewer+) |

## Layout

```
config/        Django project (settings split, urls, celery, asgi/wsgi)
apps/
  core/        TimeStamped/UUID mixins, AuditLog, MinRole permissions
  accounts/    User (extends AbstractUser), Role, UserRole
  assets/      Asset, NIC, Disk, AssetType, owner history
  agents/      Agent, AgentCommand + JWT auth
  scanning/    ScanSession + pydantic schemas + ingest service
  api/         DRF v1: agents.py, assets.py, auth.py, serializers/
docker/        Dockerfile + nginx config
```

## Development

```bash
# without Docker
python -m venv .venv && source .venv/Scripts/activate
pip install -r requirements/dev.txt
export DJANGO_SETTINGS_MODULE=config.settings.local
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

## What's NOT in MVP

Per design: remote shell, software inventory, patch management, monitoring,
alerting, multi-tenant SaaS. Architecture leaves clean upgrade paths.
