from django import forms
from django.contrib import admin
from django.db import models
from django.utils.formats import date_format
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django_boosted import AdminBoostModel

from .history import with_history

from ..helpers import _TIMELINE_EXCLUDED_DATA_TYPES
from ..models.data import OrganizationAtlasData, OrganizationAtlasDataType
from ..models.source import ORGANIZATIONATLAS_FIELDS_AUDIT, ORGANIZATIONATLAS_FIELDS_SOURCE
from ..models.temporal import ORGANIZATIONATLAS_FIELDS_TEMPORAL


@admin.display(description=_('Start date'), ordering='start_at')
def start_at_display(obj):
    if obj is None or obj.pk is None:
        return ''
    if obj.valid_from is None:
        return format_html(
            '{} ({})', date_format(obj.start_at), _('recorded')
        )
    return obj.start_at


@admin.register(OrganizationAtlasData)
class OrganizationAtlasDataAdmin(with_history(AdminBoostModel)):
    list_display = [
        'organization',
        'data_type',
        'value_display',
        'start_at_display',
        'valid_to',
        'data_reference',
        'created_at',
    ]
    list_filter = ["data_type", "created_at"]
    search_fields = ["organization__denomination", "data_type__data_type", "value"]
    readonly_fields = [
        *ORGANIZATIONATLAS_FIELDS_AUDIT,
        *ORGANIZATIONATLAS_FIELDS_TEMPORAL,
        "source_label",
        "value_type",
        "data_reference",
        "start_at_display",
    ]
    start_at_display = staticmethod(start_at_display)
    raw_id_fields = ["organization"]

    @admin.display(description=_('Value'))
    def value_display(self, obj):
        if obj.file:
            return format_html('<a href="{}">{}</a>', obj.file.url, obj.file.name)
        return obj.value

    @admin.display(description=_("Value type"))
    def value_type(self, obj):
        if obj is None or not obj.data_type_id:
            return ""
        return obj.data_type.value_type

    def lookup_allowed(self, lookup, value, request=None):
        if lookup in {"data_type__data_type", "reference__code"}:
            return True
        return super().lookup_allowed(lookup, value, request)

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .with_data_reference()
            .with_start_at()
        )

    def change_fieldsets(self):
        self.add_to_fieldset(
            None,
            (
                'organization',
                'data_type',
                'value_type',
                'value',
                'file',
                'main',
                'valid_from',
                'start_at_display',
                'valid_to',
                'data_reference',
            ),
        )
        self.add_to_fieldset(_("Source"), ORGANIZATIONATLAS_FIELDS_SOURCE)


@admin.register(OrganizationAtlasDataType)
class OrganizationAtlasDataTypeAdmin(with_history(AdminBoostModel)):
    list_display = ["data_type", "value_type", "category"]
    list_filter = ["value_type", "category"]
    search_fields = ["data_type"]

    def change_fieldsets(self):
        self.add_to_fieldset(None, ("data_type", "value_type", "category"))


class OrganizationAtlasDataInline(admin.TabularInline):
    model = OrganizationAtlasData
    formfield_overrides = {
        models.TextField: {'widget': forms.Textarea(attrs={'rows': 1})},
    }
    show_change_link = True
    extra = 1
    fields = [
        'data_type',
        'value',
        'file',
        'main',
        'start_at_display',
        'data_reference',
        'older_count',
        'source_label',
    ]
    readonly_fields = [
        'start_at_display',
        'data_reference',
        'older_count',
        'source_label',
    ]
    start_at_display = staticmethod(start_at_display)

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .active()
            .exclude(data_type__data_type__in=_TIMELINE_EXCLUDED_DATA_TYPES)
            .with_data_reference()
            .with_older_count()
            .with_start_at()
        )

    @admin.display(description=_("Older"))
    def older_count(self, obj):
        if obj is None or not obj.pk:
            return ""
        return obj.sql_older_count
