from urllib.parse import urlencode

from django.contrib import admin, messages
from django.core.management.base import CommandError
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django_boosted import AdminBoostModel, admin_boost_view

from .history import with_history

from ..managers.reference import FEATURE_CATEGORY
from ..models.feature import OrganizationAtlasFeatureManager
from ..models.reference import OrganizationAtlasReference, OrganizationAtlasReferenceCategory
from ..services.reference import configured_features, load_configured_features


class OrganizationAtlasFeatureManagerInline(admin.TabularInline):
    model = OrganizationAtlasFeatureManager
    show_change_link = True
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

    def _changelist_url(self):
        opts = self.model._meta
        return reverse(
            f"admin:{opts.app_label}_{opts.model_name}_changelist",
            current_app=self.admin_site.name,
        )

    def _loaded_features_url(self):
        opts = OrganizationAtlasReference._meta
        changelist = reverse(
            f"admin:{opts.app_label}_{opts.model_name}_changelist",
            current_app=self.admin_site.name,
        )
        category = (
            OrganizationAtlasReferenceCategory.objects.filter(name=FEATURE_CATEGORY)
            .order_by("country_code")
            .first()
        )
        if category is None:
            return changelist
        return f"{changelist}?{urlencode({'category__id__exact': category.pk})}"

    @admin_boost_view(
        "confirm",
        _("Load features"),
        requires_object=False,
        permission="change",
    )
    def load_features(self, request, confirmed=False):
        try:
            features = configured_features()
        except CommandError as error:
            messages.error(request, str(error))
            return redirect(self._changelist_url())
        if not features:
            messages.warning(
                request,
                _("No features are configured in ORGANIZATIONATLAS_FEATURES."),
            )
            return redirect(self._changelist_url())
        if confirmed:
            created_count, updated_count = load_configured_features(features)
            messages.success(
                request,
                _("Loaded %(created)s created and %(updated)s updated features.")
                % {"created": created_count, "updated": updated_count},
            )
            return redirect(self._loaded_features_url())
        codes = ", ".join(feature["code"] for feature in features)
        return {
            "confirm": _("Load or update features from settings: %(codes)s?") % {"codes": codes},
        }
