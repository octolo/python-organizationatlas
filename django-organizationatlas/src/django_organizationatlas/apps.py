"""Django app configuration."""

from django.apps import AppConfig
from django.core.exceptions import ImproperlyConfigured


class DjangoOrganizationatlasConfig(AppConfig):
    """Configuration for the django_organizationatlas app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "django_organizationatlas"
    verbose_name = "Organization Atlas"

    def ready(self):
        self.register_simple_history()

    def register_simple_history(self):
        """Track every concrete model."""
        try:
            from simple_history import register
        except ImportError as exc:
            raise ImproperlyConfigured(
                "django-simple-history is required. Install django-organizationatlas."
            ) from exc
        if not self.apps.is_installed("simple_history"):
            raise ImproperlyConfigured("Add 'simple_history' to INSTALLED_APPS.")
        for model in list(self.get_models()):
            if not model._meta.managed or model._meta.proxy:
                continue
            if getattr(model._meta, "simple_history_manager_attribute", None):
                continue
            register(
                model,
                app=self.name,
                table_name=f"oa_hist_{model._meta.model_name}",
            )

