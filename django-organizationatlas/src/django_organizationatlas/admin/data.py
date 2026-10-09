from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django_boosted import AdminBoostModel

from .history import with_history

from ..models.data import OrganizationAtlasData, OrganizationAtlasDataType
from ..models.source import ORGANIZATIONATLAS_FIELDS_AUDIT, ORGANIZATIONATLAS_FIELDS_SOURCE


@admin.register(OrganizationAtlasData)
class OrganizationAtlasDataAdmin(with_history(AdminBoostModel)):
    list_display = ["organization", "data_type", "value", "created_at"]
    list_filter = ["data_type", "created_at"]
    search_fields = ["organization__denomination", "data_type__data_type", "value"]
    readonly_fields = [*ORGANIZATIONATLAS_FIELDS_AUDIT, "source_label", "value_type"]
    raw_id_fields = ["organization"]

    @admin.display(description=_("Value type"))
    def value_type(self, obj):
        if obj is None or not obj.data_type_id:
            return ""
        return obj.data_type.value_type

    def change_fieldsets(self):
        self.add_to_fieldset(None, ('organization', 'data_type', 'value_type', 'value', ))
        self.add_to_fieldset(_("Source"), ORGANIZATIONATLAS_FIELDS_SOURCE)


@admin.register(OrganizationAtlasDataType)
class OrganizationAtlasDataTypeAdmin(with_history(AdminBoostModel)):
    list_display = ["data_type", "value_type"]
    list_filter = ["value_type"]
    search_fields = ["data_type"]

    def change_fieldsets(self):
        self.add_to_fieldset(None, ("data_type", "value_type"))


class OrganizationAtlasDataInline(admin.TabularInline):
    model = OrganizationAtlasData
    extra = 1
    fields = ["data_type", "value", "source_label"]
    readonly_fields = ["source_label"]
