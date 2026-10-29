from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django_boosted import AdminBoostModel

from .history import with_history

from ..helpers import _TIMELINE_EXCLUDED_DATA_TYPES
from ..models.data import OrganizationAtlasData, OrganizationAtlasDataType
from ..models.source import ORGANIZATIONATLAS_FIELDS_AUDIT, ORGANIZATIONATLAS_FIELDS_SOURCE
from ..models.temporal import ORGANIZATIONATLAS_FIELDS_TEMPORAL


@admin.register(OrganizationAtlasData)
class OrganizationAtlasDataAdmin(with_history(AdminBoostModel)):
    list_display = ["organization", "data_type", "value", "valid_from", "valid_to", "data_reference", "created_at"]
    list_filter = ["data_type", "created_at"]
    search_fields = ["organization__denomination", "data_type__data_type", "value"]
    readonly_fields = [
        *ORGANIZATIONATLAS_FIELDS_AUDIT,
        *ORGANIZATIONATLAS_FIELDS_TEMPORAL,
        "source_label",
        "value_type",
        "data_reference",
    ]
    raw_id_fields = ["organization"]

    @admin.display(description=_("Value type"))
    def value_type(self, obj):
        if obj is None or not obj.data_type_id:
            return ""
        return obj.data_type.value_type

    def lookup_allowed(self, lookup, value, request=None):
        if lookup == "data_type__data_type":
            return True
        return super().lookup_allowed(lookup, value, request)

    def get_queryset(self, request):
        return super().get_queryset(request).with_data_reference()

    def change_fieldsets(self):
        self.add_to_fieldset(
            None,
            ("organization", "data_type", "value_type", "value", "valid_from", "valid_to", "data_reference"),
        )
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
    fields = ["data_type", "value", "valid_from", "data_reference", "older_count", "source_label"]
    readonly_fields = ["valid_from", "data_reference", "older_count", "source_label"]

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .filter(valid_to__isnull=True)
            .exclude(data_type__data_type__in=_TIMELINE_EXCLUDED_DATA_TYPES)
            .with_data_reference()
            .with_older_count()
        )

    @admin.display(description=_("Older"))
    def older_count(self, obj):
        if obj is None or not obj.pk:
            return ""
        return obj.sql_older_count
