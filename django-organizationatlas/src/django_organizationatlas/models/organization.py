"""Organization models with international and country-specific data."""

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _
from namedid.fields import NamedIDField

from ..fields import RichTextField
from ..managers.organization import OrganizationAtlasOrganizationManager
from .source import OrganizationAtlasSourceBase

ORGANIZATIONATLAS_FIELDS_COMPANY = [
    "denomination",
    "short_denomination",
    "code",
    "named_id",
    "organization_type",
    "website",
    "resume",
]


class OrganizationAtlasOrganization(OrganizationAtlasSourceBase):
    """Organization model - parent model for organization data, documents, and events."""
    denomination = models.CharField(
        max_length=255,
        verbose_name=_("Denomination"),
        help_text=_("Organization denomination"),
    )
    short_denomination = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name=_("Short denomination"),
        help_text=_("Short organization denomination"),
    )
    code = models.CharField(
        max_length=255,
        verbose_name=_("Code"),
        help_text=_("Organization code"),
    )
    named_id = NamedIDField(
        source_fields=["pref_denomination", "code"],
        verbose_name=_("Named ID"),
        help_text=_("Named ID"),
    )
    organization_type = models.ForeignKey(
        "django_organizationatlas.OrganizationAtlasReference",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="organizations",
        limit_choices_to={"category__name": "organization_type"},
        verbose_name=_("Organization Type"),
        help_text=_("Functional classification of the legal entity"),
    )
    website = models.URLField(
        blank=True,
        null=True,
        verbose_name=_("Website"),
        help_text=_("Organization website"),
    )
    resume = RichTextField(
        blank=True,
        null=True,
        verbose_name=_("Resume"),
        help_text=_("Organization resume"),
    )

    objects = OrganizationAtlasOrganizationManager()

    class Meta:
        verbose_name = _("Organization")
        verbose_name_plural = _("Organizations")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["-created_at"]),
        ]

    def __str__(self):
        return f"{self.denomination} - {self.code}"

    @property
    def pref_denomination(self):
        return self.short_denomination or self.denomination

    @property
    def headquarters_address(self):
        return self.to_organizationatlasaddress.filter(is_headquarters=True).first()

    def clean(self):
        if self.organization_type_id and self.organization_type.category.name != "organization_type":
            raise ValidationError(
                {"organization_type": _("Reference must belong to the 'organization_type' category.")}
            )

    def enrich(self, force: bool = False) -> bool:
        return False
