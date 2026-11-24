from urllib.parse import quote

from django.contrib import admin, messages
from django.core.management.base import CommandError
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django_boosted import AdminBoostModel

from ...models.reference import (
    OrganizationAtlasReference,
    OrganizationAtlasReferenceCategory,
)
from ...models.virtuals.reference import OrganizationAtlasReferenceFixture
from ...services.reference import (
    CATEGORY_FIXTURE_SUFFIX,
    import_library_fixture,
    resolve_fixture,
)
from ._base import ReadOnlyVirtualAdmin


@admin.register(OrganizationAtlasReferenceFixture)
class OrganizationAtlasReferenceFixtureAdmin(ReadOnlyVirtualAdmin, AdminBoostModel):
    list_display = ["name", "directory", "load_fixture"]
    list_display_links = None
    list_filter = ["directory"]
    search_fields = ["path", "directory", "name"]
    actions = ["load_fixtures"]

    def has_module_permission(self, request):
        return False

    def _target_admin(self, request):
        model = getattr(
            request, '_organizationatlas_library_model', OrganizationAtlasReference,
        )
        return self.admin_site._registry.get(model)

    def has_view_permission(self, request, obj=None):
        target_admin = self._target_admin(request)
        return target_admin is not None and target_admin.has_change_permission(request)

    def get_queryset(self, request):
        target_admin = self._target_admin(request)
        queryset = super().get_queryset(request)
        if target_admin is None:
            return queryset.none()
        return queryset.filter(name__endswith=target_admin.fixture_suffix)

    @admin.action(description=_("Load"))
    def load_fixtures(self, request, queryset):
        target_admin = self._target_admin(request)
        if target_admin is None or not target_admin.has_change_permission(request):
            messages.error(request, _('You do not have permission to import data.'))
            return None
        created_count = 0
        updated_count = 0
        for fixture in queryset:
            try:
                path = resolve_fixture(fixture.path, target_admin.fixture_suffix)
                created, updated = import_library_fixture(
                    path, target_admin.fixture_suffix,
                )
            except (CommandError, UnicodeDecodeError) as error:
                messages.error(request, str(error))
                return None
            created_count += created
            updated_count += updated
        return redirect(
            target_admin._import_success(request, created_count, updated_count)
        )

    @admin.display(description=_("Load"))
    def load_fixture(self, obj):
        model = (
            OrganizationAtlasReferenceCategory
            if obj.name.endswith(CATEGORY_FIXTURE_SUFFIX)
            else OrganizationAtlasReference
        )
        opts = model._meta
        url = reverse(
            f'admin:{opts.app_label}_{opts.model_name}_import_library_file',
            current_app=self.admin_site.name,
        )
        return format_html(
            '<a class="button" href="{}?fixture={}">{}</a>',
            url,
            quote(obj.path, safe="/"),
            _("Load"),
        )
