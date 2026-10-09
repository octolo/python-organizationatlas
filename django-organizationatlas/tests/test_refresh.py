from types import SimpleNamespace

import pytest

from django_organizationatlas.helpers import refresh_organization
from django_organizationatlas.models import (
    OrganizationAtlasAddress,
    OrganizationAtlasData,
    OrganizationAtlasDataType,
    OrganizationAtlasOrganization,
)


def _virtual(**attrs):
    fields = [SimpleNamespace(name=name) for name in attrs]
    obj = SimpleNamespace(**attrs)
    obj._meta = SimpleNamespace(get_fields=lambda: fields)
    return obj


@pytest.mark.django_db
def test_refresh_updates_diff_and_keeps_previous_address():
    organization = OrganizationAtlasOrganization.objects.create(
        denomination="Old",
        code="917432254",
        source="INSEE",
        country_code="FR",
    )
    siren = OrganizationAtlasData.objects.create(
        organization=organization,
        source="INSEE",
        country_code="FR",
        data_type=OrganizationAtlasDataType.for_key("siren"),
        value="917432254",
    )
    ape = OrganizationAtlasData.objects.create(
        organization=organization,
        source="INSEE",
        country_code="FR",
        data_type=OrganizationAtlasDataType.for_key("ape"),
        value="6201Z",
    )
    previous = OrganizationAtlasAddress.objects.create(
        organization=organization,
        source="INSEE",
        country_code="FR",
        address={"address_line1": "1 rue A", "postal_code": "75001", "city": "Paris"},
        is_headquarters=True,
    )
    virtual = _virtual(
        denomination="New",
        reference="917432254",
        source_field="siren",
        country_code="FR",
        backend="INSEE SIRENE",
        address_json={"address_line1": "2 rue B", "postal_code": "69001", "city": "Lyon"},
        ape="6311Z",
        capital="1000",
        data_source='{"siren": "917432254"}',
    )

    refresh_organization(organization, virtual)

    organization.refresh_from_db()
    assert organization.denomination == "New"
    assert organization.code == "917432254"
    assert organization.source == "INSEE SIRENE"
    siren.refresh_from_db()
    assert siren.value == "917432254"
    ape.refresh_from_db()
    assert ape.value == "6311Z"
    capital = organization.to_organizationatlasdata.get(data_type__data_type="capital")
    assert capital.value == "1000"
    assert capital.data_type.value_type == "str"
    trace = organization.to_organizationatlasdata.get(data_type__data_type="apitrace")
    assert trace.organization_id == organization.pk
    assert trace.data_type.value_type == "json"
    assert trace.value == '{"siren": "917432254"}'
    previous.refresh_from_db()
    assert previous.is_headquarters is False
    current = organization.to_organizationatlasaddress.get(is_headquarters=True)
    assert current.pk != previous.pk
    assert current.address["city"] == "Lyon"


@pytest.mark.django_db
def test_refresh_leaves_headquarters_when_address_is_unchanged():
    organization = OrganizationAtlasOrganization.objects.create(
        denomination="Same",
        code="917432254",
        source="INSEE",
        country_code="FR",
    )
    address = {"address_line1": "1 rue A", "postal_code": "75001", "city": "Paris"}
    previous = OrganizationAtlasAddress.objects.create(
        organization=organization,
        source="INSEE",
        country_code="FR",
        address=address,
        is_headquarters=True,
    )
    virtual = _virtual(
        denomination="Same",
        reference="917432254",
        source_field="siren",
        country_code="FR",
        backend="INSEE",
        address_json=address,
    )

    refresh_organization(organization, virtual)

    previous.refresh_from_db()
    assert previous.is_headquarters is True
    assert organization.to_organizationatlasaddress.count() == 1
