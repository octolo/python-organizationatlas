from django.contrib import admin, messages
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django_boosted import AdminBoostModel, admin_boost_view

from .history import with_history

from ..forms.organization import (
    OrganizationRefreshForm,
    organization_provider_choices,
    organization_provider_initial,
)
from ..helpers import fetch_organization_for_refresh, refresh_organization
from ..models.organization import ORGANIZATIONATLAS_FIELDS_COMPANY, OrganizationAtlasOrganization
from ..models.source import ORGANIZATIONATLAS_FIELDS_AUDIT, ORGANIZATIONATLAS_FIELDS_SOURCE
from .address import OrganizationAtlasAddressInline
from .data import OrganizationAtlasDataInline
from .related_object import OrganizationAtlasRelatedObjectInline


@admin.register(OrganizationAtlasOrganization)
class OrganizationAtlasOrganizationAdmin(with_history(AdminBoostModel)):
    list_display = ["denomination", "code", "headquarters_address_display", "created_at"]
    list_filter = ["created_at"]
    search_fields = ["denomination", "code", "to_organizationatlasdata__value"]
    readonly_fields = ["named_id", *ORGANIZATIONATLAS_FIELDS_AUDIT, "source_label"]
    inlines = [
        OrganizationAtlasDataInline,
        OrganizationAtlasAddressInline,
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
