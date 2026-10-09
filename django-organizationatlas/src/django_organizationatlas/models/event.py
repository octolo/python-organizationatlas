from django.db import models
from django.utils.translation import gettext_lazy as _

from .organization import OrganizationAtlasOrganization
from .source import OrganizationAtlasSourceBase


class OrganizationAtlasEvent(OrganizationAtlasSourceBase):
    """Organization events from various backends."""

    organization = models.ForeignKey(
        OrganizationAtlasOrganization,
        on_delete=models.CASCADE,
        related_name="events",
        verbose_name=_("Organization"),
        help_text=_("Organization this event belongs to"),
    )
    event_type = models.CharField(
        max_length=100,
        verbose_name=_("Event Type"),
        help_text=_("Type of event (e.g., status_change, modification, capital_change)"),
    )
    title = models.CharField(
        max_length=255,
        verbose_name=_("Title"),
        help_text=_("Event title"),
    )
    date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Date"),
        help_text=_("Event date"),
    )
    description = models.TextField(
        blank=True,
        verbose_name=_("Description"),
        help_text=_("Event description"),
    )


    class Meta:
        verbose_name = _("Event")
        verbose_name_plural = _("Events")
        indexes = [
            models.Index(fields=["organization", "country_code"]),
            models.Index(fields=["event_type"]),
            models.Index(fields=["date"]),
        ]

    def __str__(self):
        return f"{self.organization.denomination} - {self.source} - {self.event_type}"
