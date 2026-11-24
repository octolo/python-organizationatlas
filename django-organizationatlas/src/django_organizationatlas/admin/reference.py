from io import TextIOWrapper

from django.contrib import admin, messages
from django.core.management.base import CommandError
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django_boosted import AdminBoostModel, admin_boost_view

from .history import with_history

from ..forms.reference import ReferenceImportForm
from ..models.reference import OrganizationAtlasReference, OrganizationAtlasReferenceCategory
from ..models.source import ORGANIZATIONATLAS_FIELDS_AUDIT, ORGANIZATIONATLAS_FIELDS_SOURCE
from ..models.virtuals.reference import OrganizationAtlasReferenceFixture
from ..services.reference import (
    CATEGORY_FIXTURE_SUFFIX,
    REFERENCE_FIXTURE_SUFFIX,
    import_library_fixture,
    import_reference_rows,
    resolve_fixture,
)
from ..services.reference_csv import read_csv_file


base_fields = [
    "category",
    "source_category",
    "code",
    "display_code",
    "description",
    "default_value",
    "characteristics",
    "priority",
    "used_count",
]


class _LibraryImportMixin:
    def _changelist_url(self):
        opts = self.model._meta
        return reverse(
            f"admin:{opts.app_label}_{opts.model_name}_changelist",
            current_app=self.admin_site.name,
        )

    def _import_success(self, request, created_count, updated_count):
        messages.success(
            request,
            _('Imported %(created)s created and %(updated)s updated rows.')
            % {'created': created_count, 'updated': updated_count},
        )
        return self._changelist_url()

    @admin_boost_view(
        'list',
        _('Import from library'),
        requires_object=False,
        permission='change',
    )
    def import_from_library(self, request):
        request._organizationatlas_library_model = self.model
        fixture_admin = self.admin_site._registry[OrganizationAtlasReferenceFixture]
        return fixture_admin.changelist_view(
            request,
            extra_context={'title': _('Import from library')},
        )

    @admin_boost_view(
        'confirm',
        _('Import from library'),
        requires_object=False,
        permission='change',
        hidden=True,
    )
    def import_library_file(self, request, confirmed=False):
        if not self.has_change_permission(request):
            messages.error(request, _('You do not have permission to import data.'))
            return redirect(self._changelist_url())
        relative = request.GET.get('fixture', '')
        try:
            csv_path = resolve_fixture(relative, self.fixture_suffix)
        except CommandError:
            messages.error(request, _('Unknown fixture.'))
            return redirect(self._changelist_url())
        if confirmed:
            try:
                created, updated = import_library_fixture(
                    csv_path, self.fixture_suffix,
                )
            except (CommandError, UnicodeDecodeError) as error:
                messages.error(request, str(error))
                return redirect(self._changelist_url())
            return redirect(self._import_success(request, created, updated))
        return {'confirm': _('Load or reload %(path)s?') % {'path': relative}}


@admin.register(OrganizationAtlasReferenceCategory)
class OrganizationAtlasReferenceCategoryAdmin(
    _LibraryImportMixin, with_history(AdminBoostModel),
):
    fixture_suffix = CATEGORY_FIXTURE_SUFFIX
    list_display = [
        "name", "description", "country_code", 'unique', "reference_count",
    ]
    list_filter = ["country_code", 'unique']
    search_fields = ["name", "description", "country_code"]
    readonly_fields = ["reference_count"]

    def get_queryset(self, request):
        return super().get_queryset(request).with_reference_count()

    @admin.display(description=_("References"), ordering="sql_reference_count")
    def reference_count(self, obj):
        return getattr(obj, "sql_reference_count", "—")

    def change_fieldsets(self):
        self.add_to_fieldset(
            None,
            ["name", "description", "country_code", 'unique', "reference_count"],
        )


@admin.register(OrganizationAtlasReference)
class OrganizationAtlasReferenceAdmin(
    _LibraryImportMixin, with_history(AdminBoostModel),
):
    fixture_suffix = REFERENCE_FIXTURE_SUFFIX
    list_display = ["code_label", "description", "characteristics", "priority", "used_count"]
    list_filter = ["category__country_code", "category"]
    search_fields = [
        "category__name",
        "category__country_code",
        "code",
        "display_code",
        "description",
        "characteristics",
    ]
    readonly_fields = [*ORGANIZATIONATLAS_FIELDS_AUDIT, "source_label", "used_count"]
    raw_id_fields = ["category", "source_category"]

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("category", "source_category")
            .with_usage_count()
        )

    @admin.display(description=_("Code"), ordering="code")
    def code_label(self, obj):
        if obj is None:
            return ""
        category = str(obj.category) if obj.category_id else ""
        return self.format_with_help_text(
            self.format_label(obj.display_code), category,
        )

    def used_count(self, obj):
        return getattr(obj, "sql_used_count", "—")
    used_count.short_description = _("Used count")
    used_count.admin_order_field = "sql_used_count"

    def change_fieldsets(self):
        self.add_to_fieldset(None, base_fields)
        self.add_to_fieldset(_("Source"), ORGANIZATIONATLAS_FIELDS_SOURCE)

    @admin_boost_view(
        "adminform",
        _("Import from CSV"),
        requires_object=False,
        permission="change",
    )
    def import_from_csv(self, request, form=None):
        if request.method == "POST" and form is not None and form.is_valid():
            uploaded_file = form.cleaned_data["csv_file"]
            try:
                uploaded_file.seek(0)
                with TextIOWrapper(uploaded_file.file, encoding="utf-8") as text_file:
                    rows = read_csv_file(text_file)
                created_count, updated_count = import_reference_rows(rows)
            except UnicodeDecodeError:
                messages.error(request, _("CSV file must be encoded in UTF-8."))
                return {"form": form}
            except CommandError as error:
                messages.error(request, str(error))
                return {"form": form}
            return {"redirect_url": self._import_success(request, created_count, updated_count)}
        return {"form": ReferenceImportForm()}
