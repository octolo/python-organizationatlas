"""Organization models with international and country-specific data."""

from django.contrib.contenttypes.fields import GenericRelation
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _
from namedid.fields import NamedIDField

from ..fields import RichTextField
from ..managers.organization import OrganizationAtlasOrganizationManager
from .source import OrganizationAtlasSourceBase

def _rule_reference_filters(category: str, code: str) -> dict:
    """Split ``fr/DECISIONS`` into a country and a category name."""
    raw = (category or "").strip()
    country_code, separator, name = raw.partition("/")
    if not separator:
        name = raw
        country_code = ""
    filters = {
        "code": (code or "").strip(),
        "category__name": name.strip(),
    }
    if country_code.strip():
        filters["category__country_code__iexact"] = country_code.strip()
    else:
        filters["category__country_code"] = ""
    return filters


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
        source_fields=["truncate_denomination", "code"],
        max_length=40,
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
    stakeholder_relations_as_holder = GenericRelation(
        "django_organizationatlas.OrganizationAtlasStakeholderRelation",
        related_query_name="holder_organization",
    )

    objects: OrganizationAtlasOrganizationManager = OrganizationAtlasOrganizationManager()

    class Meta:
        verbose_name = _("Organization")
        verbose_name_plural = _("Organizations")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["-created_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["country_code", "code"],
                nulls_distinct=False,
                name="unique_organization_country_code",
            ),
        ]

    def __str__(self):
        return f"{self.denomination} - {self.code}"

    @property
    def pref_denomination(self):
        return self.short_denomination or self.denomination

    @property
    def truncate_denomination(self):
        """Short name when set, otherwise the denomination, cut to fit in named_id."""
        name = self.short_denomination or self.denomination or ""
        code = self.code or ""
        field = self._meta.get_field("named_id")
        reserved = len(code) + (len(field.separator) if code else 0)
        limit = max(field.max_length - reserved, 0)
        return name[:limit]

    @property
    def headquarters_address(self):
        return self.to_organizationatlasaddress.filter(
            is_headquarters=True,
            valid_to__isnull=True,
        ).first()

    def rule_value(self, category: str, code: str) -> str:
        """Current value of a company rule, or the reference default when none is set."""
        from .reference import OrganizationAtlasReference

        reference = OrganizationAtlasReference.objects.filter(
            **_rule_reference_filters(category, code),
        ).order_by("-priority").first()
        if reference is None:
            return ""
        current = (
            self.to_organizationatlasdata.filter(reference=reference, valid_to__isnull=True)
            .order_by("-created_at", "-pk")
            .values_list("value", flat=True)
            .first()
        )
        value = (current or "").strip()
        if value:
            return value
        return reference.default_value

    def clean(self):
        if self.organization_type_id and self.organization_type.category.name != "organization_type":
            raise ValidationError(
                {"organization_type": _("Reference must belong to the 'organization_type' category.")}
            )

    def enrich(self) -> bool:
        from ..helpers import fetch_organization_for_refresh, refresh_organization

        if not self.code or not self.source:
            return False
        virtual = fetch_organization_for_refresh(self.code, self.source)
        has_result = getattr(virtual, "denomination", None) or getattr(
            virtual,
            "reference",
            None,
        )
        if virtual is None or not has_result:
            return False
        refresh_organization(self, virtual)
        return True
