from django.db import models
from django.utils.translation import gettext_lazy as _
from virtualqueryset.models import VirtualModel

from ...managers.virtuals.reference import OrganizationAtlasReferenceFixtureManager


class OrganizationAtlasReferenceFixture(VirtualModel):
    """One CSV file from the packaged reference library."""

    path = models.CharField(
        max_length=255,
        primary_key=True,
        verbose_name=_("Path"),
    )
    directory = models.CharField(
        max_length=255,
        verbose_name=_("Directory"),
    )
    name = models.CharField(
        max_length=255,
        verbose_name=_("File"),
    )

    objects = OrganizationAtlasReferenceFixtureManager()

    class Meta:
        managed = False
        verbose_name = _("Reference fixture")
        verbose_name_plural = _("Reference fixtures")
        ordering = ["directory", "name"]

    def __str__(self):
        return self.path
