from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django_boosted import AdminBoostModel

from .history import with_history

from ..models.relation import OrganizationAtlasOrganizationRelation
from ..models.source import ORGANIZATIONATLAS_FIELDS_AUDIT, ORGANIZATIONATLAS_FIELDS_SOURCE


class OrganizationAtlasOrganizationRelationInline(admin.TabularInline):
    model = OrganizationAtlasOrganizationRelation
    fk_name = "from_organization"
    extra = 1
    fields = ["to_organization", "relation_type", "other", "source_label"]
    readonly_fields = ["source_label"]
    raw_id_fields = ["to_organization"]


@admin.register(OrganizationAtlasOrganizationRelation)
class OrganizationAtlasOrganizationRelationAdmin(with_history(AdminBoostModel)):
    list_display = [
        "from_organization",
        "relation_type",
        "to_organization",
        "source_label",
        "created_at",
    ]
    list_filter = ["relation_type", "created_at"]
    search_fields = [
        "from_organization__denomination",
        "from_organization__code",
        "to_organization__denomination",
        "to_organization__code",
        "other",
    ]
    readonly_fields = [*ORGANIZATIONATLAS_FIELDS_AUDIT, "source_label"]
    raw_id_fields = ["from_organization", "to_organization"]

    def change_fieldsets(self):
        self.add_to_fieldset(
            None,
            ["from_organization", "to_organization", "relation_type", "other", "valid_from", "valid_to"],
        )
        self.add_to_fieldset(_("Source"), ORGANIZATIONATLAS_FIELDS_SOURCE)
