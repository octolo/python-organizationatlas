from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django_boosted import AdminBoostModel

from .history import with_history

from ..models.address import OrganizationAtlasAddress
from ..models.source import ORGANIZATIONATLAS_FIELDS_AUDIT, ORGANIZATIONATLAS_FIELDS_SOURCE


class OrganizationAtlasAddressInline(admin.TabularInline):
    model = OrganizationAtlasAddress
    extra = 1
    fields = ["address", "is_headquarters", "source_label"]
    readonly_fields = ["source_label"]


@admin.register(OrganizationAtlasAddress)
class OrganizationAtlasAddressAdmin(with_history(AdminBoostModel)):
    list_display = [
        "organization",
        "source_label",
        "address_display",
        "is_headquarters",
        "created_at",
    ]
    list_filter = ["source", "country_code", "is_headquarters", "created_at"]
    search_fields = ["organization__denomination", "organization__to_organizationatlasdata__value"]
    readonly_fields = [*ORGANIZATIONATLAS_FIELDS_AUDIT, "source_label"]
    raw_id_fields = ["organization"]

    def change_fieldsets(self):
        self.add_to_fieldset(None, ("organization", "address", "is_headquarters"))
        self.add_to_fieldset(_("source"), ORGANIZATIONATLAS_FIELDS_SOURCE)

    def address_display(self, obj: OrganizationAtlasAddress) -> str:
        return str(obj.address) if obj.address else "-"
    address_display.short_description = _("Address")
