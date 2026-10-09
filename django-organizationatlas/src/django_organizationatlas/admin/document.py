from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from ..models.document import OrganizationAtlasDocument
from .history import with_history
from ..models.source import ORGANIZATIONATLAS_FIELDS_AUDIT


class OrganizationDocumentInline(admin.TabularInline):
    model = OrganizationAtlasDocument
    extra = 1
    fields = ["source_label", "document_type", "title", "date", "url"]
    readonly_fields = ["source_label"]


@admin.register(OrganizationAtlasDocument)
class OrganizationDocumentAdmin(with_history(admin.ModelAdmin)):
    list_display = [
        "organization",
        "source_label",
        "document_type",
        "title",
        "date",
        "created_at",
    ]
    list_filter = ["source", "country_code", "document_type", "date", "created_at"]
    search_fields = ["organization__denomination", "title", "document_type", "source"]
    readonly_fields = [*ORGANIZATIONATLAS_FIELDS_AUDIT, "source_label"]

    fieldsets = (
        (
            _("Document"),
            {
                "fields": (
                    "organization",
                    "source_label",
                    "document_type",
                    "title",
                    "date",
                    "url",
                )
            },
        ),
        (_("Content"), {"fields": ("content",)}),
        (
            _("Metadata"),
            {"fields": ("metadata", *ORGANIZATIONATLAS_FIELDS_AUDIT), "classes": ("collapse",)},
        ),
    )

