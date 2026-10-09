from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db.models import Q
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django_boosted import AdminBoostModel, admin_boost_view, get_current_user

from .history import with_history

from ..fields import RichTextField
from ..forms.organization import (
    OrganizationRefreshForm,
    organization_provider_choices,
    organization_provider_initial,
)
from ..helpers import fetch_organization_for_refresh, refresh_organization
from ..models.data import OrganizationAtlasData, OrganizationAtlasDataType
from ..models.organization import ORGANIZATIONATLAS_FIELDS_COMPANY, OrganizationAtlasOrganization
from ..models.reference import OrganizationAtlasReference
from ..models.source import (
    ORGANIZATIONATLAS_FIELDS_AUDIT,
    ORGANIZATIONATLAS_FIELDS_SOURCE,
    USER_COUNTRY_CODE,
)
from .address import OrganizationAtlasAddressInline
from .data import OrganizationAtlasDataInline
from .related_object import OrganizationAtlasRelatedObjectInline
from .relation import OrganizationAtlasOrganizationRelationInline


@admin.register(OrganizationAtlasOrganization)
class OrganizationAtlasOrganizationAdmin(with_history(AdminBoostModel)):
    list_display = ["denomination", "code", "headquarters_address_display", "created_at"]
    list_display_links = ["denomination"]
    list_filter = ["created_at"]
    search_fields = ["denomination", "code", "to_organizationatlasdata__value"]
    readonly_fields = ["named_id", *ORGANIZATIONATLAS_FIELDS_AUDIT, "source_label"]
    inlines = [
        OrganizationAtlasDataInline,
        OrganizationAtlasAddressInline,
        OrganizationAtlasOrganizationRelationInline,
        OrganizationAtlasRelatedObjectInline,
    ]
    changeform_actions = {
        "refresh_person": _("Refresh Persons"),
        "refresh_address": _("Refresh Addresses"),
        "refresh_data": _("Refresh Data"),
        "refresh_event": _("Refresh Events"),
        "refresh_document": _("Refresh Documents"),
        "full_refresh": _("Full Refresh"),
    }

    def get_queryset(self, request):
        return super().get_queryset(request).with_headquarters()

    def get_search_results(self, request, queryset, search_term):
        queryset, use_distinct = super().get_search_results(request, queryset, search_term)
        return queryset.distinct(), use_distinct

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if isinstance(db_field, RichTextField):
            kwargs.setdefault("required", False)
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    def change_fieldsets(self):
        self.add_to_fieldset(None, ORGANIZATIONATLAS_FIELDS_COMPANY)
        self.add_to_fieldset(_("Source"), ORGANIZATIONATLAS_FIELDS_SOURCE)

    def headquarters_address_display(self, obj: OrganizationAtlasOrganization) -> str:
        prefetched = getattr(obj, "prefetched_headquarters", None)
        if prefetched:
            return str(prefetched[0].address)
        return "-"
    headquarters_address_display.short_description = _("Headquarters Address")

    def handle_refresh_person(self, request, object_id):
        print("ok")

    @admin_boost_view("adminform", _("Refresh"))
    def refresh(self, request, obj, form=None):
        if request.method == "POST" and form is not None and form.is_valid():
            provider_name = form.cleaned_data["provider"]
            try:
                virtual = fetch_organization_for_refresh(obj.code, provider_name)
            except Exception as exc:
                messages.error(request, _("Refresh failed: %(error)s") % {"error": exc})
                return {"form": form}
            has_result = getattr(virtual, "denomination", None) or getattr(virtual, "reference", None)
            if virtual is None or not has_result:
                messages.error(
                    request,
                    _("This provider returned no organization for %(code)s.") % {"code": obj.code},
                )
                return {"form": form}
            refresh_organization(obj, virtual)
            messages.success(request, _("Organization refreshed."))
            url = reverse(
                "admin:django_organizationatlas_organizationatlasorganization_change",
                args=[obj.pk],
            )
            return {"redirect_url": url}
        choices = organization_provider_choices()
        initial = organization_provider_initial(obj.source, choices)
        return {"form": OrganizationRefreshForm(initial={"provider": initial})}

    @admin_boost_view("message", _("Search Organization"))
    def search_organization(self, request):
        return redirect("admin:django_organizationatlas_organizationatlasvirtualorganization_changelist")

    def _organization_admin_url(self, name, *args, query=None):
        opts = self.model._meta
        url = reverse(
            f"admin:{opts.app_label}_{opts.model_name}_{name}",
            args=args,
            current_app=self.admin_site.name,
        )
        if query:
            return f"{url}?{query}"
        return url

    def _deny_data_change(self, request, obj):
        if self.has_change_permission(request, obj):
            return None
        messages.error(request, _("You do not have permission to add data."))
        return redirect(self._organization_admin_url("change", obj.pk))

    def _save_added_data(self, request, obj, *, data_type_name, value, reference=None):
        max_length = OrganizationAtlasDataType._meta.get_field("data_type").max_length
        if len(data_type_name) > max_length:
            messages.error(request, _("Data type name is too long."))
            return None
        row = OrganizationAtlasData(
            organization=obj,
            data_type=OrganizationAtlasDataType.for_key(data_type_name),
            value=value,
        )
        user = get_current_user()
        if user is not None and user.is_authenticated and user.pk:
            row.source = row._manual_source(user)
            row.country_code = USER_COUNTRY_CODE
        try:
            row.clean()
            row.save()
        except (ValidationError, IntegrityError):
            messages.error(
                request,
                _("An open data of this type already exists for this organization."),
            )
            return None
        if reference is not None:
            row.reference.add(reference)
        messages.success(request, _("Data added."))
        return self._organization_admin_url("change", obj.pk)

    @admin_boost_view(
        "list",
        _("Add data from references"),
        requires_object=True,
        permission="change",
    )
    def add_data_references(self, request, obj):
        denied = self._deny_data_change(request, obj)
        if denied is not None:
            return denied
        queryset = (
            OrganizationAtlasReference.objects.select_related("category")
            .with_has_data_type()
            .filter(has_data_type=True)
        )
        term = request.GET.get("q", "").strip()
        if term:
            queryset = queryset.filter(
                Q(code__icontains=term)
                | Q(description__icontains=term)
                | Q(category__name__icontains=term)
            )

        def reference_code(reference):
            return reference.code
        reference_code.short_description = _("Code")

        def reference_description(reference):
            return reference.description
        reference_description.short_description = _("Description")

        def reference_category(reference):
            return str(reference.category) if reference.category_id else ""
        reference_category.short_description = _("Category")

        def add_reference_button(reference):
            url = self._organization_admin_url(
                "add_reference_data",
                obj.pk,
                query=f"reference={reference.pk}",
            )
            return format_html('<a class="button" href="{}">{}</a>', url, _("Add"))
        add_reference_button.short_description = _("Add")

        return {
            "queryset": queryset,
            "list_display": [
                reference_code,
                reference_description,
                reference_category,
                add_reference_button,
            ],
            "search_fields": ["code", "description", "category__name"],
            "actions_on_top": False,
            "actions_on_bottom": False,
        }

    @admin_boost_view(
        "redirect",
        _("Add"),
        requires_object=True,
        permission="change",
        hidden=True,
    )
    def add_reference_data(self, request, obj):
        denied = self._deny_data_change(request, obj)
        if denied is not None:
            return denied
        try:
            reference_id = int(request.GET.get("reference") or "")
        except (TypeError, ValueError):
            reference_id = None
        reference = None
        if reference_id is not None:
            reference = (
                OrganizationAtlasReference.objects.select_related("category")
                .with_has_data_type()
                .filter(has_data_type=True, pk=reference_id)
                .first()
            )
        list_url = self._organization_admin_url("add_data_references", obj.pk)
        if reference is None:
            messages.error(request, _("Unknown reference."))
            return list_url
        saved_url = self._save_added_data(
            request,
            obj,
            data_type_name=reference.category.name,
            value=reference.code,
            reference=reference,
        )
        return saved_url or list_url
