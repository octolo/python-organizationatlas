import logging
from datetime import date

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError
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
    OrganizationHistoryForm,
    OrganizationRefreshForm,
    history_provider_choices,
    organization_provider_choices,
    organization_provider_initial,
)
from ..helpers import (
    _API_HISTORY_TRACE,
    _API_TRACE,
    _TIMELINE_EXCLUDED_DATA_TYPES,
    fetch_organization_for_refresh,
    load_organization_history,
    refresh_organization,
)
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
from .person import OrganizationAtlasPersonInline
from .related_object import OrganizationAtlasRelatedObjectInline
from .relation import OrganizationAtlasOrganizationRelationInline

logger = logging.getLogger(__name__)


class _TimelineAddress:
    """Address row shaped like organization data so the timeline can mix both."""

    def __init__(self, address):
        self.valid_from = address.valid_from
        self.valid_to = address.valid_to
        self.data_type = "headquarters" if address.is_headquarters else "address"
        self.value = str(address.address or "")
        self.data_reference = ""
        self._source_label = address.source_label()

    def source_label(self):
        return self._source_label


def _timeline_entries(organization):
    data = (
        organization.to_organizationatlasdata.select_related("data_type")
        .with_data_reference()
        .exclude(data_type__data_type__in=_TIMELINE_EXCLUDED_DATA_TYPES)
    )
    entries = list(data)
    for address in organization.to_organizationatlasaddress.all():
        if not str(address.address or "").strip():
            continue
        entries.append(_TimelineAddress(address))
    entries.sort(
        key=lambda row: (
            row.valid_from is None,
            row.valid_from or date.min,
            str(row.data_type),
        )
    )
    return entries


def _timeline_groups(rows):
    groups = []
    current_start = object()
    current = None
    for row in rows:
        if row.valid_from != current_start:
            current_start = row.valid_from
            current = {"valid_from": row.valid_from, "rows": []}
            groups.append(current)
        current["rows"].append(row)
    return groups


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
        OrganizationAtlasPersonInline,
        OrganizationAtlasOrganizationRelationInline,
        OrganizationAtlasRelatedObjectInline,
    ]

    def has_change_permission(self, request, obj=None):
        return admin.ModelAdmin.has_change_permission(self, request, obj)

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

    @admin_boost_view("adminform", _("Refresh"))
    def refresh(self, request, obj, form=None):
        if not self.has_change_permission(request, obj):
            raise PermissionDenied
        if request.method == "POST" and form is not None and form.is_valid():
            provider_name = form.cleaned_data["provider"]
            try:
                virtual = fetch_organization_for_refresh(obj.code, provider_name)
            except Exception:
                logger.exception(
                    "Organization refresh failed",
                    extra={"organization_id": obj.pk, "provider": provider_name},
                )
                messages.error(request, _("Organization refresh failed."))
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

    @admin_boost_view("adminform", _("Load history"), permission="change")
    def load_history(self, request, obj, form=None):
        if not self.has_change_permission(request, obj):
            raise PermissionDenied
        choices = history_provider_choices()
        if request.method == "POST" and form is not None and form.is_valid():
            provider_name = form.cleaned_data["provider"]
            try:
                count = load_organization_history(obj, provider_name)
            except Exception:
                logger.exception(
                    "Organization history load failed",
                    extra={"organization_id": obj.pk, "provider": provider_name},
                )
                messages.error(request, _("Organization history load failed."))
                return {"form": form}
            if not count:
                messages.error(
                    request,
                    _("This provider returned no history for %(code)s.") % {"code": obj.code},
                )
                return {"form": form}
            messages.success(
                request,
                _("Loaded %(count)s history values.") % {"count": count},
            )
            url = reverse(
                "admin:django_organizationatlas_organizationatlasorganization_change",
                args=[obj.pk],
            )
            return {"redirect_url": url}
        if not choices:
            messages.error(request, _("No provider exposes organization history."))
            return redirect(self._organization_admin_url("change", obj.pk))
        initial = organization_provider_initial(obj.source, choices)
        if not initial and len(choices) == 1:
            initial = choices[0][0]
        return {"form": OrganizationHistoryForm(initial={"provider": initial})}

    @admin_boost_view(
        "message",
        _("Timeline"),
        template_name="django_organizationatlas/timeline.html",
    )
    def timeline(self, request, obj):
        return {"groups": _timeline_groups(_timeline_entries(obj))}

    @admin_boost_view("redirect", _("List data"))
    def list_data(self, request, obj):
        url = reverse("admin:django_organizationatlas_organizationatlasdata_changelist")
        return f"{url}?organization_id={obj.pk}"

    def _data_list_url(self, organization, data_type):
        url = reverse("admin:django_organizationatlas_organizationatlasdata_changelist")
        return f"{url}?organization_id={organization.pk}&data_type__data_type={data_type}"

    @admin_boost_view("redirect", _("API trace"))
    def list_api_trace(self, request, obj):
        return self._data_list_url(obj, _API_TRACE)

    @admin_boost_view("redirect", _("API history"))
    def list_api_history(self, request, obj):
        return self._data_list_url(obj, _API_HISTORY_TRACE)

    @admin_boost_view("redirect", _("List address"))
    def list_address(self, request, obj):
        url = reverse("admin:django_organizationatlas_organizationatlasaddress_changelist")
        return f"{url}?organization_id={obj.pk}"

    @admin_boost_view("redirect", _("List relations"))
    def list_relations(self, request, obj):
        url = reverse("admin:django_organizationatlas_organizationatlasorganizationrelation_changelist")
        return f"{url}?from_organization_id={obj.pk}"

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
        _("Add data"),
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
        "confirm",
        _("Add"),
        requires_object=True,
        permission="change",
        hidden=True,
    )
    def add_reference_data(self, request, obj, confirmed=False):
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
            return redirect(list_url)
        if not confirmed:
            return {
                "confirm": _(
                    "Add reference %(reference)s to %(organization)s?"
                )
                % {"reference": reference, "organization": obj},
            }
        saved_url = self._save_added_data(
            request,
            obj,
            data_type_name=reference.category.name,
            value=reference.code,
            reference=reference,
        )
        return redirect(saved_url or list_url)
