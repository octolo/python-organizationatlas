from types import SimpleNamespace

import pytest
from django.contrib import admin
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.test import RequestFactory
from django.urls import reverse

from django_organizationatlas.admin.virtuals.organization import (
    OrganizationAtlasVirtualOrganizationAdmin,
)
from django_organizationatlas.models import (
    OrganizationAtlasData,
    OrganizationAtlasDataType,
    OrganizationAtlasOrganization,
)
from django_organizationatlas.models.virtuals.organization import (
    OrganizationAtlasVirtualOrganization,
)


def _admin():
    return OrganizationAtlasVirtualOrganizationAdmin(
        OrganizationAtlasVirtualOrganization,
        admin.site,
    )


@pytest.mark.django_db
def test_create_organization_requires_add_permission():
    request = RequestFactory().post("/")
    request.user = User.objects.create_user("viewer", password="password")
    model_admin = _admin()

    with pytest.raises(PermissionDenied):
        model_admin.handle_create_organization(request, "917432254")


@pytest.mark.django_db
def test_show_organization_redirects_to_persisted_primary_key():
    organization = OrganizationAtlasOrganization.objects.create(
        denomination="Octolo",
        code="internal-code",
        source="insee",
        country_code="FR",
    )
    OrganizationAtlasData.objects.create(
        organization=organization,
        data_type=OrganizationAtlasDataType.for_key("siren"),
        value="917432254",
        source="insee",
        country_code="FR",
    )
    virtual = SimpleNamespace(source_field="siren", reference="917432254")
    model_admin = _admin()
    model_admin.get_object = lambda request, object_id: virtual

    response = model_admin.handle_show_organization(
        RequestFactory().get("/"),
        "917432254",
    )

    assert response.url == reverse(
        "admin:django_organizationatlas_organizationatlasorganization_change",
        args=[organization.pk],
    )


@pytest.mark.django_db
def test_create_organization_rejects_existing_reference():
    organization = OrganizationAtlasOrganization.objects.create(
        denomination="Octolo",
        code="917432254",
        source="insee",
        country_code="FR",
    )
    OrganizationAtlasData.objects.create(
        organization=organization,
        data_type=OrganizationAtlasDataType.for_key("siren"),
        value="917432254",
        source="insee",
        country_code="FR",
    )
    virtual = SimpleNamespace(source_field="siren", reference="917432254")
    request = RequestFactory().post("/")
    request.user = User.objects.create_superuser("admin", password="password")
    model_admin = _admin()
    model_admin.get_object = lambda request, object_id: virtual

    with pytest.raises(PermissionDenied):
        model_admin.handle_create_organization(request, "917432254")


@pytest.mark.django_db
def test_create_organization_returns_404_when_reference_disappeared():
    request = RequestFactory().post("/")
    request.user = User.objects.create_superuser("admin", password="password")
    model_admin = _admin()
    model_admin.get_object = lambda request, object_id: None

    with pytest.raises(Http404):
        model_admin.handle_create_organization(request, "917432254")
