import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from django_organizationatlas.models import (
    OrganizationAtlasData,
    OrganizationAtlasDataType,
    OrganizationAtlasOrganization,
    OrganizationAtlasReference,
    OrganizationAtlasReferenceCategory,
)
from django_organizationatlas.models.source import USER_COUNTRY_CODE


def _organization():
    return OrganizationAtlasOrganization.objects.create(
        denomination="Octolo",
        code="917432254",
        source="INSEE",
        country_code="FR",
    )


def _client():
    user = User.objects.create_superuser("ada", "ada@example.com", "password")
    client = Client()
    client.force_login(user)
    return client, user


def _url(name, organization, query=""):
    url = reverse(
        f"admin:django_organizationatlas_organizationatlasorganization_{name}",
        args=[organization.pk],
    )
    if query:
        return f"{url}?{query}"
    return url


@pytest.mark.django_db
def test_organization_detail_opens_reference_list():
    organization = _organization()
    client, _user = _client()

    change = client.get(_url("change", organization))
    content = change.content.decode()
    assert "Add data from references" in content
    assert _url("add_data_references", organization) in content


@pytest.mark.django_db
def test_reference_has_data_type_matches_category_name():
    typed = OrganizationAtlasReferenceCategory.objects.create(name="ape", country_code="FR")
    untyped = OrganizationAtlasReferenceCategory.objects.create(name="legalform", country_code="FR")
    OrganizationAtlasDataType.for_key("ape")
    matching = OrganizationAtlasReference.objects.create(
        category=typed,
        code="6201Z",
        description="Programmation",
        source="INSEE",
        country_code="FR",
    )
    OrganizationAtlasReference.objects.create(
        category=untyped,
        code="5710",
        description="SAS",
        source="INSEE",
        country_code="FR",
    )

    found = set(
        OrganizationAtlasReference.objects.with_has_data_type()
        .filter(has_data_type=True)
        .values_list("pk", flat=True)
    )

    assert found == {matching.pk}


@pytest.mark.django_db
def test_add_reference_data_lists_typed_references_and_adds_one():
    organization = _organization()
    client, _user = _client()
    typed = OrganizationAtlasReferenceCategory.objects.create(name="ape", country_code="FR")
    untyped = OrganizationAtlasReferenceCategory.objects.create(name="legalform", country_code="FR")
    OrganizationAtlasDataType.for_key("ape")
    reference = OrganizationAtlasReference.objects.create(
        category=typed,
        code="6201Z",
        description="Programmation",
        source="INSEE",
        country_code="FR",
    )
    OrganizationAtlasReference.objects.create(
        category=untyped,
        code="5710",
        description="SAS",
        source="INSEE",
        country_code="FR",
    )

    page = client.get(_url("add_data_references", organization))
    assert page.status_code == 200
    content = page.content.decode()
    assert "Programmation" in content
    assert "SAS" not in content
    add_url = _url("add_reference_data", organization, f"reference={reference.pk}")
    assert add_url in content

    response = client.get(add_url)
    assert response.status_code == 302
    assert response.url == _url("change", organization)

    row = organization.to_organizationatlasdata.get()
    assert row.data_type.data_type == "ape"
    assert row.value == "6201Z"
    assert list(row.reference.all()) == [reference]


@pytest.mark.django_db
def test_add_reference_data_rejects_an_open_duplicate():
    organization = _organization()
    client, user = _client()
    category = OrganizationAtlasReferenceCategory.objects.create(name="ape", country_code="FR")
    OrganizationAtlasDataType.for_key("ape")
    reference = OrganizationAtlasReference.objects.create(
        category=category,
        code="6201Z",
        description="Programmation",
        source="INSEE",
        country_code="FR",
    )
    OrganizationAtlasData.objects.create(
        organization=organization,
        data_type=OrganizationAtlasDataType.for_key("ape"),
        value="6201Z",
        source=str(user.pk),
        country_code=USER_COUNTRY_CODE,
    )

    response = client.get(
        _url("add_reference_data", organization, f"reference={reference.pk}"),
        follow=True,
    )

    assert response.status_code == 200
    assert organization.to_organizationatlasdata.count() == 1
    assert "already exists" in response.content.decode()
