from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from ..models.event import OrganizationAtlasEvent
from .history import with_history
from ..models.source import ORGANIZATIONATLAS_FIELDS_AUDIT


class OrganizationEventInline(admin.TabularInline):
    model = OrganizationAtlasEvent
    extra = 1
    fields = ["source_label", "event_type", "title", "date"]
    readonly_fields = ["source_label"]


@admin.register(OrganizationAtlasEvent)
class OrganizationEventAdmin(with_history(admin.ModelAdmin)):
    list_display = [
        "organization",
        "source_label",
        "event_type",
        "title",
        "date",
        "created_at",
    ]
    list_filter = ["source", "country_code", "event_type", "date", "created_at"]
    search_fields = ["organization__denomination", "title", "event_type", "source"]
    readonly_fields = [*ORGANIZATIONATLAS_FIELDS_AUDIT, "source_label"]

    fieldsets = (
        (
            _("Event"),
            {"fields": ("organization", "source_label", "event_type", "title", "date")},
        ),
        (_("Description"), {"fields": ("description",)}),
        (
            _("Metadata"),
            {"fields": ("metadata", *ORGANIZATIONATLAS_FIELDS_AUDIT), "classes": ("collapse",)},
        ),
    )

