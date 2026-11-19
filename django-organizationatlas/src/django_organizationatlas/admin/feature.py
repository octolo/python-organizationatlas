from django.contrib import admin
from django_boosted import AdminBoostModel

from .history import with_history

from ..models.feature import OrganizationAtlasFeatureManager
from ..models.reference import OrganizationAtlasReference


class OrganizationAtlasFeatureManagerInline(admin.TabularInline):
    model = OrganizationAtlasFeatureManager
    extra = 0
    fields = [
        "feature",
        "role",
        "enabled",
        "level",
    ]

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "feature":
            kwargs["queryset"] = OrganizationAtlasReference.objects.features()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(OrganizationAtlasFeatureManager)
class OrganizationAtlasFeatureManagerAdmin(with_history(AdminBoostModel)):
    list_display = ["organization", "feature", "role", "level", "enabled"]
    list_filter = ["role", "level", "enabled"]
    search_fields = [
        "organization__denomination",
        "organization__code",
        "feature__code",
        "feature__description",
    ]
    raw_id_fields = ["organization"]

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "feature":
            kwargs["queryset"] = OrganizationAtlasReference.objects.features()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def change_fieldsets(self):
        self.add_to_fieldset(None, ["organization", "feature", "role", "enabled", "level"])
