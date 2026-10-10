from django.apps import AppConfig


class MomanyiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'momanyi'
    verbose_name = 'Forest Resource Monitoring'

    def ready(self):
        from . import signals  # noqa: F401  (connects cache invalidation)
