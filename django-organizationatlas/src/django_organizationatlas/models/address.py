"""Organization address models."""

from django.db import models
from django.utils.translation import gettext_lazy as _
from django_geoaddress.fields import GeoaddressField

from .organization import OrganizationAtlasOrganization
from .source import OrganizationAtlasSourceBase
from .temporal import TemporalValidityMixin


class OrganizationAtlasAddress(TemporalValidityMixin, OrganizationAtlasSourceBase):
    """Organization addresses from various backends."""

    organization = models.ForeignKey(
        OrganizationAtlasOrganization,
        on_delete=models.CASCADE,
        related_name="to_organizationatlasaddress",
        verbose_name=_("Organization"),
        help_text=_("Organization this address belongs to"),
    )
    address = GeoaddressField(
        verbose_name=_("Address"),
        help_text=_("Organization address"),
    )
    is_headquarters = models.BooleanField(
        default=False,
        verbose_name=_("Is headquarters"),
        help_text=_("Whether this address is the organization's headquarters"),
    )

    class Meta:
        verbose_name = _("Address")
        verbose_name_plural = _("Addresses")
        indexes = [
            models.Index(fields=["organization", "address"]),
            models.Index(fields=["organization", "is_headquarters"]),
        ]
        ordering = ["-is_headquarters", "-created_at"]

    def __str__(self):
        return f"{self.organization.denomination} - {self.address}"
