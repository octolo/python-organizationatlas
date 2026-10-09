from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _
from django_boosted import AuditMixin, get_current_user

ORGANIZATIONATLAS_FIELDS_AUDIT = [
    "created_by",
    "updated_by",
    "created_at",
    "updated_at",
]

ORGANIZATIONATLAS_FIELDS_SOURCE = [
    "source_label",
    "metadata",
    *ORGANIZATIONATLAS_FIELDS_AUDIT,
]

# ISO 3166-1 alpha-2 user-assigned code: not a country.
USER_COUNTRY_CODE = "XX"

class OrganizationAtlasSourceBase(AuditMixin):
    """Abstract base class for organization-related models with source and country."""

    source = models.CharField(
        max_length=100,
        verbose_name=_("Source"),
        help_text=_("Backend name, or the user id when the record is entered manually."),
        blank=True,
        null=True,
        editable=False,
    )
    country_code = models.CharField(
        max_length=2,
        verbose_name=_("Country Code"),
        help_text=_("ISO country code. XX means the record was entered by a user."),
        blank=True,
        null=True,
        editable=False,
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("Metadata"),
        help_text=_("Additional metadata"),
    )

    class Meta:
        abstract = True

    def _manual_source(self, user) -> str:
        attr = getattr(settings, "ORGANIZATIONATLAS_USER_SOURCE", "pk") or "pk"
        if attr == "id":
            attr = "pk"
        value = getattr(user, attr, None)
        if value in (None, ""):
            value = user.pk
        return str(value)

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")
        filled = []
        if not self.source:
            user = get_current_user()
            if user is not None and user.is_authenticated and user.pk:
                self.source = self._manual_source(user)
                filled.append("source")
                if not self.country_code:
                    self.country_code = USER_COUNTRY_CODE
                    filled.append("country_code")
        if update_fields is not None and filled:
            kwargs["update_fields"] = list(dict.fromkeys([*update_fields, *filled]))
        super().save(*args, **kwargs)

    def source_label(self) -> str:
        parts = [part for part in (self.country_code, self.source) if part]
        return "/".join(parts) if parts else "-"
    source_label.short_description = _("Source")
