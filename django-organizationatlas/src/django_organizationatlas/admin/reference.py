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
from ..services.reference import (
    import_reference_rows,
    list_fixtures,
    read_csv,
    read_csv_file,
    resolve_fixture,
)

base_fields = [
    "category",
    "code",
    "description",
    "characteristics",
    "priority",
    "used_count",
]


@admin.register(OrganizationAtlasReferenceCategory)
class OrganizationAtlasReferenceCategoryAdmin(with_history(AdminBoostModel)):
    list_display = ["name", "country_code", "reference_count"]
    list_filter = ["country_code"]
    search_fields = ["name", "country_code"]
    readonly_fields = ["reference_count"]

    def get_queryset(self, request):
        return super().get_queryset(request).with_reference_count()

    @admin.display(description=_("References"), ordering="sql_reference_count")
    def reference_count(self, obj):
        return getattr(obj, "sql_reference_count", "—")

    def change_fieldsets(self):
        self.add_to_fieldset(None, ["name", "country_code", "reference_count"])


@admin.register(OrganizationAtlasReference)
class OrganizationAtlasReferenceAdmin(with_history(AdminBoostModel)):
    list_display = ["code_label", "description", "characteristics", "priority", "used_count"]
    list_filter = ["category__country_code", "category"]
    search_fields = [
        "category__name",
        "category__country_code",
        "code",
        "description",
        "characteristics",
    ]
    readonly_fields = [*ORGANIZATIONATLAS_FIELDS_AUDIT, "source_label", "used_count"]
    raw_id_fields = ["category"]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("category").with_usage_count()

    @admin.display(description=_("Code"), ordering="code")
    def code_label(self, obj):
        if obj is None:
            return ""
        category = str(obj.category) if obj.category_id else ""
        return self.format_with_help_text(self.format_label(obj.code), category)

    def used_count(self, obj):
        return getattr(obj, "sql_used_count", "—")
    used_count.short_description = _("Used count")
    used_count.admin_order_field = "sql_used_count"

    def change_fieldsets(self):
        self.add_to_fieldset(None, base_fields)
        self.add_to_fieldset(_("Source"), ORGANIZATIONATLAS_FIELDS_SOURCE)

    def _changelist_url(self):
        opts = self.model._meta
        return reverse(
            f"admin:{opts.app_label}_{opts.model_name}_changelist",
            current_app=self.admin_site.name,
        )

    def _import_success(self, request, created_count, updated_count):
        messages.success(
            request,
            _("Imported %(created)s created and %(updated)s updated reference rows.")
            % {"created": created_count, "updated": updated_count},
        )
        return self._changelist_url()

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

    @admin_boost_view(
        "message",
        _("Import from library"),
        requires_object=False,
        permission="change",
        template_name="django_organizationatlas/reference_library.html",
    )
    def import_from_library(self, request):
        opts = self.model._meta
        return {
            "fixtures": list_fixtures(),
            "confirm_url": reverse(
                f"admin:{opts.app_label}_{opts.model_name}_import_library_file",
                current_app=self.admin_site.name,
            ),
        }

    @admin_boost_view(
        "confirm",
        _("Import from library"),
        requires_object=False,
        permission="change",
        hidden=True,
    )
    def import_library_file(self, request, confirmed=False):
        if not self.has_change_permission(request):
            messages.error(request, _("You do not have permission to import reference data."))
            return redirect(self._changelist_url())
        relative = request.GET.get("fixture", "")
        try:
            csv_path = resolve_fixture(relative)
        except CommandError:
            messages.error(request, _("Unknown fixture."))
            return redirect(self._changelist_url())
        if confirmed:
            try:
                created_count, updated_count = import_reference_rows(read_csv(csv_path))
            except (CommandError, UnicodeDecodeError) as error:
                messages.error(request, str(error))
                return redirect(self._changelist_url())
            return redirect(self._import_success(request, created_count, updated_count))
        return {"confirm": _("Load or reload %(path)s?") % {"path": relative}}
