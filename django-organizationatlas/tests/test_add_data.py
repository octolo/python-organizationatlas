import re
from datetime import date

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from django_organizationatlas.models import (
    OrganizationAtlasAddress,
    OrganizationAtlasData,
    OrganizationAtlasDataType,
    OrganizationAtlasOrganization,
    OrganizationAtlasOrganizationRelation,
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
def test_list_data_opens_data_admin_for_the_organization():
    organization = _organization()
    other = OrganizationAtlasOrganization.objects.create(
        denomination="Other",
        code="111111111",
        source="insee",
        country_code="FR",
    )
    OrganizationAtlasData.objects.create(
        organization=organization,
        data_type=OrganizationAtlasDataType.for_key("denomination"),
        value="kept-value",
        source="insee",
        country_code="FR",
    )
    OrganizationAtlasData.objects.create(
        organization=other,
        data_type=OrganizationAtlasDataType.for_key("denomination"),
        value="hidden-value",
        source="insee",
        country_code="FR",
    )
    client, _user = _client()

    change = client.get(_url("change", organization))
    assert "List data" in change.content.decode()
    assert _url("list_data", organization) in change.content.decode()

    response = client.get(_url("list_data", organization))
    assert response.status_code == 302
    assert response.url.endswith(f"?organization_id={organization.pk}")

    page = client.get(response.url)
    html = page.content.decode()
    assert page.status_code == 200
    assert "kept-value" in html
    assert "hidden-value" not in html


@pytest.mark.django_db
def test_data_inline_hides_traces_and_links_to_filtered_lists():
    organization = _organization()
    OrganizationAtlasData.objects.create(
        organization=organization,
        data_type=OrganizationAtlasDataType.for_key("denomination"),
        value="visible-name",
        source="insee",
        country_code="FR",
    )
    OrganizationAtlasData.objects.create(
        organization=organization,
        data_type=OrganizationAtlasDataType.for_key("apitrace", "json"),
        value="secret-api-trace",
        source="insee",
        country_code="FR",
    )
    OrganizationAtlasData.objects.create(
        organization=organization,
        data_type=OrganizationAtlasDataType.for_key("apihistorytrace", "json"),
        value="secret-history-trace",
        source="insee",
        country_code="FR",
    )
    client, _user = _client()

    change = client.get(_url("change", organization))
    change_html = change.content.decode()
    assert "visible-name" in change_html
    assert "secret-api-trace" not in change_html
    assert "secret-history-trace" not in change_html
    assert "API trace" in change_html
    assert "API history" in change_html

    api_trace = client.get(_url("list_api_trace", organization))
    assert api_trace.status_code == 302
    assert api_trace.url.endswith(
        f"?organization_id={organization.pk}&data_type__data_type=apitrace"
    )
    api_html = client.get(api_trace.url).content.decode()
    assert "secret-api-trace" in api_html
    assert "secret-history-trace" not in api_html
    assert "visible-name" not in api_html

    history = client.get(_url("list_api_history", organization))
    assert history.status_code == 302
    assert history.url.endswith(
        f"?organization_id={organization.pk}&data_type__data_type=apihistorytrace"
    )
    history_html = client.get(history.url).content.decode()
    assert "secret-history-trace" in history_html
    assert "secret-api-trace" not in history_html
    assert "visible-name" not in history_html


@pytest.mark.django_db
def test_data_inline_shows_current_rows_and_counts_older_ones():
    organization = _organization()
    denomination = OrganizationAtlasDataType.for_key("denomination")
    ape = OrganizationAtlasDataType.for_key("ape")
    OrganizationAtlasData.objects.create(
        organization=organization,
        data_type=denomination,
        value="former-name",
        valid_from=date(2010, 1, 1),
        valid_to=date(2019, 12, 31),
        source="insee",
        country_code="FR",
    )
    OrganizationAtlasData.objects.create(
        organization=organization,
        data_type=denomination,
        value="current-name",
        valid_from=date(2020, 1, 1),
        source="insee",
        country_code="FR",
    )
    OrganizationAtlasData.objects.create(
        organization=organization,
        data_type=ape,
        value="current-ape-a",
        source="insee",
        country_code="FR",
    )
    OrganizationAtlasData.objects.create(
        organization=organization,
        data_type=ape,
        value="current-ape-b",
        source="other",
        country_code="FR",
    )
    client, _user = _client()

    html = client.get(_url("change", organization)).content.decode()

    assert "current-name" in html
    assert "current-ape-a" in html
    assert "current-ape-b" in html
    assert "former-name" not in html
    older_counts = re.findall(r'class="field-older_count">\s*<p>(\d+)</p>', html)
    assert sorted(older_counts) == ["0", "0", "1"]


@pytest.mark.django_db
def test_list_address_and_relations_filter_by_organization():
    organization = _organization()
    other = OrganizationAtlasOrganization.objects.create(
        denomination="Other",
        code="111111111",
        source="INSEE",
        country_code="FR",
    )
    target = OrganizationAtlasOrganization.objects.create(
        denomination="Target Co",
        code="222222222",
        source="INSEE",
        country_code="FR",
    )
    hidden_target = OrganizationAtlasOrganization.objects.create(
        denomination="Hidden Co",
        code="333333333",
        source="INSEE",
        country_code="FR",
    )
    OrganizationAtlasAddress.objects.create(
        organization=organization,
        source="insee",
        country_code="FR",
        address={"address_line1": "1 rue Kept"},
    )
    OrganizationAtlasAddress.objects.create(
        organization=other,
        source="insee",
        country_code="FR",
        address={"address_line1": "9 rue Hidden"},
    )
    OrganizationAtlasOrganizationRelation.objects.create(
        from_organization=organization,
        to_organization=target,
        source="insee",
        country_code="FR",
    )
    OrganizationAtlasOrganizationRelation.objects.create(
        from_organization=other,
        to_organization=hidden_target,
        source="insee",
        country_code="FR",
    )
    client, _user = _client()
    change = client.get(_url("change", organization))
    html = change.content.decode()
    assert "List address" in html
    assert "List relations" in html

    address = client.get(_url("list_address", organization), follow=True)
    address_html = address.content.decode()
    assert "1 rue Kept" in address_html
    assert "9 rue Hidden" not in address_html

    relations = client.get(_url("list_relations", organization), follow=True)
    relations_html = relations.content.decode()
    assert "Target Co" in relations_html
    assert "Hidden Co" not in relations_html


@pytest.mark.django_db
def test_timeline_groups_data_by_date_and_skips_apitrace():
    organization = _organization()
    other = OrganizationAtlasOrganization.objects.create(
        denomination="Other",
        code="111111111",
        source="INSEE",
        country_code="FR",
    )
    OrganizationAtlasData.objects.create(
        organization=organization,
        data_type=OrganizationAtlasDataType.for_key("denomination"),
        value="OLD",
        valid_from=date(2010, 1, 1),
        valid_to=date(2019, 12, 31),
        source="insee",
        country_code="FR",
    )
    OrganizationAtlasData.objects.create(
        organization=organization,
        data_type=OrganizationAtlasDataType.for_key("denomination"),
        value="NEW",
        valid_from=date(2020, 1, 1),
        source="insee",
        country_code="FR",
    )
    OrganizationAtlasData.objects.create(
        organization=organization,
        data_type=OrganizationAtlasDataType.for_key("apitrace"),
        value="secret-trace",
        valid_from=date(2020, 1, 1),
        source="insee",
        country_code="FR",
    )
    OrganizationAtlasData.objects.create(
        organization=organization,
        data_type=OrganizationAtlasDataType.for_key("apihistorytrace", "json"),
        value="history-secret",
        valid_from=date(2020, 1, 1),
        source="insee",
        country_code="FR",
    )
    OrganizationAtlasAddress.objects.create(
        organization=organization,
        source="insee",
        country_code="FR",
        address={"address_line1": "1 rue Kept", "city": "Paris"},
        is_headquarters=True,
    )
    OrganizationAtlasData.objects.create(
        organization=other,
        data_type=OrganizationAtlasDataType.for_key("denomination"),
        value="OTHER",
        valid_from=date(2010, 1, 1),
        source="insee",
        country_code="FR",
    )
    client, _user = _client()

    change = client.get(_url("change", organization))
    assert "Timeline" in change.content.decode()

    page = client.get(_url("timeline", organization))
    assert page.status_code == 200
    html = page.content.decode()
    assert html.index("2010-01-01") < html.index("2020-01-01")
    assert "OLD" in html
    assert "NEW" in html
    assert "secret-trace" not in html
    assert "history-secret" not in html
    assert "OTHER" not in html
    assert "1 rue Kept" in html
    assert "headquarters" in html


@pytest.mark.django_db
def test_organization_change_shows_person_inline():
    organization = _organization()
    client, _user = _client()

    html = client.get(_url("change", organization)).content.decode()

    assert "to_organizationatlasperson-group" in html


@pytest.mark.django_db
def test_timeline_shows_reference_description_when_the_value_matches():
    organization = _organization()
    category = OrganizationAtlasReferenceCategory.for_name("ape", "FR")
    OrganizationAtlasReference.objects.create(
        category=category,
        code="6201Z",
        description="Programmation informatique",
        country_code="FR",
        source="insee",
    )
    OrganizationAtlasData.objects.create(
        organization=organization,
        data_type=OrganizationAtlasDataType.for_key("ape"),
        value="6201Z",
        valid_from=date(2020, 1, 1),
        source="insee",
        country_code="FR",
    )
    OrganizationAtlasData.objects.create(
        organization=organization,
        data_type=OrganizationAtlasDataType.for_key("denomination"),
        value="Octolo",
        valid_from=date(2020, 1, 1),
        source="insee",
        country_code="FR",
    )
    client, _user = _client()

    html = client.get(_url("timeline", organization)).content.decode()

    assert "6201Z" in html
    assert "Programmation informatique" in html
    assert html.index("6201Z") < html.index("Programmation informatique")


@pytest.mark.django_db
def test_organization_detail_opens_reference_list():
    organization = _organization()
    client, _user = _client()

    change = client.get(_url("change", organization))
    content = change.content.decode()
    assert "Add data" in content
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
    assert response.status_code == 200
    assert not organization.to_organizationatlasdata.exists()

    response = client.post(add_url, {"action": "confirm"})
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

    add_url = _url("add_reference_data", organization, f"reference={reference.pk}")
    response = client.post(
        add_url,
        {"action": "confirm"},
        follow=True,
    )

    assert response.status_code == 200
    assert organization.to_organizationatlasdata.count() == 1
    assert "already exists" in response.content.decode()
