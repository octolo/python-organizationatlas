"""Admin for organization related objects."""

from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django_boosted import AdminBoostModel

from ..models.related_object import OrganizationAtlasRelatedObject
from .history import with_history
from ..models.source import ORGANIZATIONATLAS_FIELDS_AUDIT


class OrganizationAtlasRelatedObjectAdminMixin:
    """Link display shared by the changelist and the organization inline."""

    @admin.display(description=_("Object"))
    def object_url_link_display(self, obj):
        if not obj or not obj.content_type_id or not obj.object_id:
            return "-"
        label = obj.object_str or f"{obj.content_type} #{obj.object_id}"
        try:
            url = reverse(
                f"admin:{obj.content_type.app_label}_{obj.content_type.model}_change",
                args=[obj.object_id],
            )
        except Exception:
            return label
        return format_html('<a href="{}">{}</a>', url, label)


class OrganizationAtlasRelatedObjectInline(
    OrganizationAtlasRelatedObjectAdminMixin, admin.TabularInline
):
    """Related objects edited from the organization page."""

    model = OrganizationAtlasRelatedObject
    extra = 0
    fields = ["content_type", "object_id", "comment", "object_url_link_display"]
    readonly_fields = ["object_url_link_display"]


@admin.register(OrganizationAtlasRelatedObject)
class OrganizationAtlasRelatedObjectAdmin(
    OrganizationAtlasRelatedObjectAdminMixin, with_history(AdminBoostModel)
):
    """Admin for organization related objects."""

    list_display = [
        "organization",
        "content_type",
        "object_url_link_display",
        "created_at",
    ]
    list_filter = ["content_type", "created_at"]
    search_fields = ["organization__denomination", "organization__code", "object_str"]
    readonly_fields = ["object_str", "object_url_link_display", *ORGANIZATIONATLAS_FIELDS_AUDIT]
    raw_id_fields = ["organization"]

    def change_fieldsets(self):
        self.add_to_fieldset(
            None,
            ["organization", "content_type", "object_id", "object_url_link_display", "comment"],
        )
        self.add_to_fieldset(_("Timestamps"), ["object_str", *ORGANIZATIONATLAS_FIELDS_AUDIT])
