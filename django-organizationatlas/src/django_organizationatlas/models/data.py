"""Organization data models."""


from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from ..managers.data import OrganizationAtlasDataManager
from .organization import OrganizationAtlasOrganization
from .reference import OrganizationAtlasReference
from .source import OrganizationAtlasSourceBase
from .temporal import TemporalValidityMixin

VALUE_TYPE_CHOICES = [
    ("str", _("String")),
    ("int", _("Integer")),
    ("float", _("Float")),
    ("bool", _("Boolean")),
    ("date", _("Date")),
    ("json", _("JSON")),
]


class OrganizationAtlasDataType(models.Model):
    """Shared definition of a data key and the type of its value."""

    data_type = models.CharField(
        max_length=100,
        unique=True,
        verbose_name=_("Data Type"),
        help_text=_("Type of data (e.g., denomination, siren, capital, employees)"),
    )
    value_type = models.CharField(
        max_length=10,
        verbose_name=_("Value Type"),
        choices=VALUE_TYPE_CHOICES,
        default="str",
        help_text=_("Type of the value (str, int, float, bool, date, json)"),
    )

    class Meta:
        verbose_name = _("Data Type")
        verbose_name_plural = _("Data Types")
        ordering = ["data_type"]

    def __str__(self):
        return self.data_type

    @classmethod
    def for_key(cls, data_type: str, value_type: str = "str"):
        """Return the shared type, creating it with value_type only the first time."""
        obj, _created = cls.objects.get_or_create(
            data_type=data_type,
            defaults={"value_type": value_type},
        )
        return obj


class OrganizationAtlasData(TemporalValidityMixin, OrganizationAtlasSourceBase):
    """Organization data from various backends."""

    temporal_key_fields = ("organization", "source", "country_code", "data_type")

    organization = models.ForeignKey(
        OrganizationAtlasOrganization,
        on_delete=models.CASCADE,
        related_name="to_organizationatlasdata",
        verbose_name=_("Organization"),
        help_text=_("Organization this data belongs to"),
    )
    data_type = models.ForeignKey(
        OrganizationAtlasDataType,
        on_delete=models.PROTECT,
        related_name="records",
        verbose_name=_("Data Type"),
        help_text=_("Shared data type. Its value type applies to every record."),
    )
    value = models.TextField(
        verbose_name=_("Value"),
        help_text=_("Data value"),
    )
    reference = models.ManyToManyField(
        OrganizationAtlasReference,
        verbose_name=_("Reference"),
        help_text=_("Reference this data belongs to"),
        related_name="to_organizationatlasdata",
        blank=True,
    )

    class Meta:
        verbose_name = _("Data")
        verbose_name_plural = _("Data")
        indexes = [
            models.Index(fields=["organization", "country_code"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "source", "country_code", "data_type"],
                condition=Q(valid_to__isnull=True),
                nulls_distinct=False,
                name="unique_open_organizationatlasdata",
            ),
        ]
        ordering = ["data_type__data_type", "-created_at"]

    objects = OrganizationAtlasDataManager()

    def __str__(self):
        return (
            f"{self.organization.denomination} - {self.source} - "
            f"{self.country_code} - {self.data_type}"
        )

    def data_reference(self):
        if hasattr(self, "sql_data_reference"):
            return self.sql_data_reference or ""
        if not self.data_type_id:
            return ""
        description = (
            OrganizationAtlasReference.objects.filter(
                category__name=self.data_type.data_type,
                code=self.value,
            )
            .order_by("-priority")
            .values_list("description", flat=True)
            .first()
        )
        return description or ""
    data_reference.short_description = _("Reference")
    data_reference = property(data_reference)

    @property
    def reference_description(self):
        if hasattr(self, "sql_reference_description"):
            return self.sql_reference_description
        first = self.reference.values_list("description", flat=True).first()
        return first or ""
