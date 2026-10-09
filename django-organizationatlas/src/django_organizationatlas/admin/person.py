from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django_boosted import AdminBoostModel

from .history import with_history

from ..forms.person import OrganizationAtlasPersonForm
from ..models.person import OrganizationAtlasPerson
from ..models.source import ORGANIZATIONATLAS_FIELDS_AUDIT, ORGANIZATIONATLAS_FIELDS_SOURCE


class OrganizationAtlasPersonInline(admin.TabularInline):
    model = OrganizationAtlasPerson
    extra = 1
    fields = ["officer_or_owner", "gender", "full_name", "created_at"]
    readonly_fields = ["full_name", "created_at"]


@admin.register(OrganizationAtlasPerson)
class OrganizationAtlasPersonAdmin(with_history(AdminBoostModel)):
    form = OrganizationAtlasPersonForm
    list_display = ["organization", "officer_or_owner", "gender", "full_name", "created_at"]
    list_filter = ["officer_or_owner", "gender", "created_at"]
    search_fields = ["organization__denomination", "first_name", "last_name"]
    readonly_fields = [*ORGANIZATIONATLAS_FIELDS_AUDIT, "source_label"]
    raw_id_fields = ["organization"]

    def change_fieldsets(self):
        self.add_to_fieldset(None, [
            "organization",
            "officer_or_owner",
        ])
        self.add_to_fieldset(_("Identity"), [
            "first_name",
            "last_name",
            "gender",
            "birth_date",
        ])
        self.add_to_fieldset(_("Source"), ORGANIZATIONATLAS_FIELDS_SOURCE)
