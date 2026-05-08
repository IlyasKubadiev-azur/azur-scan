from django.shortcuts import render
from django.utils.translation import get_language

# Inline i18n for the landing page. Avoids needing .po/.mo compilation
# for a single static-ish page. For admin chrome, we rely on Django's and
# django-unfold's bundled translations via LocaleMiddleware.
LANDING_STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "subtitle": "IT Asset Inventory · MVP",
        "lede": (
            "Backend for IT asset inventory: agent-driven endpoint data "
            "collection, centralized device registry, scan history, remote "
            "rescan, RBAC and AD/LDAP integration."
        ),
        "admin_title": "Admin Panel",
        "admin_desc": (
            "Manage assets, agents, users and roles. "
            "Main interface for operators."
        ),
        "docs_title": "API Docs (Swagger)",
        "docs_desc": (
            "Interactive documentation for all endpoints: agent enroll/heartbeat/scan, "
            "asset CRUD, JWT auth."
        ),
        "api_title": "REST API v1",
        "api_desc": (
            "DRF browsable API root. Authorize via Bearer JWT — log in first "
            "at /api/v1/auth/login."
        ),
        "schema_title": "OpenAPI Schema",
        "schema_desc": (
            "Raw OpenAPI 3.0 JSON schema — for client generation or import "
            "into Postman/Insomnia."
        ),
        "health_title": "Health Check",
        "health_desc": "Liveness probe for Docker / Kubernetes / load balancer.",
        "status_running": "running",
        "signed_in_as": "signed in as",
        "theme_label": "Theme",
        "language_label": "Language",
        "tagline": "Azur-Scan · MVP",
    },
    "ru": {
        "subtitle": "Инвентаризация IT-ассетов · MVP",
        "lede": (
            "Бэкенд для учёта IT-ассетов: агентский сбор данных с эндпоинтов, "
            "централизованный реестр устройств, история сканирований, удалённый "
            "rescan, RBAC и интеграция с AD/LDAP."
        ),
        "admin_title": "Панель администратора",
        "admin_desc": (
            "Управление ассетами, агентами, пользователями и ролями. "
            "Основной интерфейс оператора."
        ),
        "docs_title": "API-документация (Swagger)",
        "docs_desc": (
            "Интерактивная документация всех endpoint'ов: agent enroll/heartbeat/scan, "
            "CRUD ассетов, JWT-авторизация."
        ),
        "api_title": "REST API v1",
        "api_desc": (
            "Browsable API root от DRF. Авторизация через Bearer JWT — сначала "
            "залогиньтесь по /api/v1/auth/login."
        ),
        "schema_title": "OpenAPI Schema",
        "schema_desc": (
            "Сырая OpenAPI 3.0 JSON-схема — для генерации клиентов или импорта "
            "в Postman/Insomnia."
        ),
        "health_title": "Health-check",
        "health_desc": "Liveness probe для Docker / Kubernetes / load balancer'а.",
        "status_running": "работает",
        "signed_in_as": "вход как",
        "theme_label": "Тема",
        "language_label": "Язык",
        "tagline": "Azur-Scan · MVP",
    },
}


def landing(request):
    """Public landing page at `/` with theme + language toggles."""
    lang = (get_language() or "en").split("-")[0]
    if lang not in LANDING_STRINGS:
        lang = "en"
    return render(request, "landing.html", {
        "t": LANDING_STRINGS[lang],
        "current_lang": lang,
        "user_authenticated": request.user.is_authenticated,
    })
