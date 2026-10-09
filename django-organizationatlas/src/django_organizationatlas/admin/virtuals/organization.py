from django.contrib import admin
from django.contrib.admin.utils import unquote
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.html import format_html
from django.utils.http import urlencode
from django.utils.translation import gettext_lazy as _
from django_boosted import AdminBoostModel
from django_providerkit.admin.filters import BackendServiceAdminFilter, FirstServiceAdminFilter

from ...models.virtuals.organization import OrganizationAtlasVirtualOrganization
from ...models.virtuals.provider import OrganizationAtlasProviderModel
from ._base import ReadOnlyVirtualAdmin

BackendServiceAdminFilter.provider_model = OrganizationAtlasProviderModel


@admin.register(OrganizationAtlasVirtualOrganization)
class OrganizationAtlasVirtualOrganizationAdmin(ReadOnlyVirtualAdmin, AdminBoostModel):
    list_display = ["denomination", "reference", "address", "backend_name_display"]
    search_fields = ["denomination",]
    list_filter = [FirstServiceAdminFilter, BackendServiceAdminFilter]
    fieldsets = [
        (None, {"fields": ("denomination", "reference", "source_field", "address")}),
    ]
    changeform_actions = {
        "create_organization": _("Create Organization"),
        "show_organization": _("Show Organization"),
        "show_organizations": _("Show Organizations"),
    }

    def change_fieldsets(self):
        self.add_to_fieldset(_("Backend"), ("backend", "backend_name_display", "organizationatlas_id"))
        self.add_to_fieldset("data", ("country_code", "data_source", "organization_count_exists"))
        self.add_to_fieldset("address", ("address_json",))

    def has_show_organization_permission(self, request, obj=None):
        return self.organization_count_exists(obj) == 1 if obj else False

    def has_show_organizations_permission(self, request, obj=None):
        return self.organization_count_exists(obj) > 1 if obj else False

    def get_queryset(self, request):
        query = request.GET.get("q")
        if query:
            kwargs = {"first": bool(request.GET.get("first"))}
            if request.GET.get("bck"):
                kwargs["attribute_search"] = {"name": request.GET.get("bck")}
            return self.model.objects.search_organization(query=query, **kwargs)
        return self.model.objects.none()

    def get_search_results(self, request, queryset, search_term):
        return queryset, False

    def get_object(self, request, object_id, from_field=None):
        _ = from_field  # Unused parameter required by Django admin interface
        object_id = unquote(object_id)
        return self.model.objects.search_organization_by_reference(code=object_id).first()

    def backend_name_display(self, obj: OrganizationAtlasVirtualOrganization | None) -> str:
        if not obj or not obj.backend or not obj.backend_name:
            return "-"
        url = reverse("admin:django_organizationatlas_organizationatlasprovidermodel_change", args=[obj.backend])
        return format_html('<a href="{}">{}</a>', url, obj.backend_name)
    backend_name_display.short_description = _("Backend name")

    def organization_model_exist(self, obj: OrganizationAtlasVirtualOrganization | None) -> bool:
        from django_organizationatlas.models.organization import OrganizationAtlasOrganization
        return OrganizationAtlasOrganization.objects.filter(denomination=obj.denomination).exists()

    def handle_create_organization(self, request, object_id):
        object_id = unquote(object_id)
        obj = self.get_object(request, object_id)
        organization = obj.create_organization()
        return redirect("admin:django_organizationatlas_organizationatlasorganization_change", organization.id)

    def handle_show_organizations(self, request, object_id):
        object_id = unquote(object_id)
        obj = self.get_object(request, object_id)
        url = reverse("admin:django_organizationatlas_organizationatlasorganization_changelist")
        query = urlencode({"q": obj.reference})
        return redirect(f"{url}?{query}")

    def handle_show_organization(self, request, object_id):
        object_id = unquote(object_id)
        obj = self.get_object(request, object_id)
        return redirect("admin:django_organizationatlas_organizationatlasorganization_change", obj.id)

    def organization_count_exists(self, obj: OrganizationAtlasVirtualOrganization | None) -> bool:
        from django_organizationatlas.models.organization import OrganizationAtlasOrganization
        return OrganizationAtlasOrganization.objects.filter(
            to_organizationatlasdata__data_type__data_type=obj.source_field,
            to_organizationatlasdata__value=obj.reference,
        ).count()
