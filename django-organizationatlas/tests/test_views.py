from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth.models import Permission, User
from django.test import Client
from django.urls import reverse

from django_organizationatlas.models import OrganizationAtlasOrganization


def _organization():
    return OrganizationAtlasOrganization.objects.create(
        denomination="Octolo",
        code="917432254",
        source="insee",
        country_code="FR",
    )


def _client(*permissions):
    user = User.objects.create_user(
        "member",
        "member@example.com",
        "password",
    )
    if permissions:
        user.user_permissions.add(
            *Permission.objects.filter(
                content_type__app_label="django_organizationatlas",
                codename__in=permissions,
            )
        )
    client = Client()
    client.force_login(user)
    return client


@pytest.mark.django_db
def test_organization_views_require_authentication():
    organization = _organization()
    client = Client()

    for url in (
        reverse("django_organizationatlas:organization-list"),
        reverse(
            "django_organizationatlas:organization-detail",
            args=[organization.pk],
        ),
    ):
        response = client.get(url)
        assert response.status_code == 302
        assert response.url.startswith("/accounts/login/")


@pytest.mark.django_db
def test_organization_list_and_detail_render():
    organization = _organization()
    client = _client("view_organizationatlasorganization")

    list_response = client.get(
        reverse("django_organizationatlas:organization-list")
    )
    detail_response = client.get(
        reverse(
            "django_organizationatlas:organization-detail",
            args=[organization.pk],
        )
    )

    assert list_response.status_code == 200
    assert "Octolo" in list_response.content.decode()
    assert detail_response.status_code == 200
    assert "917432254" in detail_response.content.decode()


@pytest.mark.django_db
def test_organization_list_and_detail_require_view_permission():
    organization = _organization()
    client = _client()

    assert client.get(
        reverse("django_organizationatlas:organization-list")
    ).status_code == 403
    assert client.get(
        reverse(
            "django_organizationatlas:organization-detail",
            args=[organization.pk],
        )
    ).status_code == 403


@pytest.mark.django_db
def test_enrich_requires_change_permission():
    organization = _organization()
    client = _client()
    url = reverse(
        "django_organizationatlas:organization-enrich",
        args=[organization.pk],
    )

    assert client.get(url).status_code == 403
    assert client.post(url).status_code == 403


@pytest.mark.django_db
def test_enrich_refreshes_organization():
    organization = _organization()
    client = _client("change_organizationatlasorganization")
    url = reverse(
        "django_organizationatlas:organization-enrich",
        args=[organization.pk],
    )

    assert client.get(url).status_code == 200
    with patch.object(
        OrganizationAtlasOrganization,
        "enrich",
        return_value=True,
    ) as enrich:
        response = client.post(url)

    assert response.status_code == 302
    assert response.url == reverse(
        "django_organizationatlas:organization-detail",
        args=[organization.pk],
    )
    enrich.assert_called_once_with()


@pytest.mark.django_db
def test_model_enrich_uses_source_provider():
    organization = _organization()
    virtual = MagicMock(denomination="Octolo updated", reference="917432254")

    with (
        patch(
            "django_organizationatlas.helpers.fetch_organization_for_refresh",
            return_value=virtual,
        ) as fetch,
        patch(
            "django_organizationatlas.helpers.refresh_organization",
        ) as refresh,
    ):
        assert organization.enrich()

    fetch.assert_called_once_with("917432254", "insee")
    refresh.assert_called_once_with(organization, virtual)
