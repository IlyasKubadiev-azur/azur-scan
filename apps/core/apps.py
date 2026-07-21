from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = "apps.core"
    label = "core"
    verbose_name = "Core"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        # Wire up audit-log signal receivers. Imported inside ready() so the
        # module loads only after Django has finished setting up the app
        # registry (avoids "Apps aren't loaded yet" errors).
        from apps.core import signals  # noqa: F401
        signals._register_asset_delete_signal()
