from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from django.utils import timezone

from django_organizationatlas.helpers import (
    apply_organization_history,
    create_organization,
    refresh_organization,
)
from django_organizationatlas.models import (
    OrganizationAtlasAddress,
    OrganizationAtlasData,
    OrganizationAtlasDataType,
    OrganizationAtlasOrganization,
    OrganizationAtlasReference,
    OrganizationAtlasReferenceCategory,
)


def _virtual(**attrs):
    fields = [SimpleNamespace(name=name) for name in attrs]
    obj = SimpleNamespace(**attrs)
    obj._meta = SimpleNamespace(get_fields=lambda: fields)
    return obj


@pytest.mark.django_db
def test_provider_data_links_reference_by_country_and_allows_unknown_values():
    france = OrganizationAtlasReferenceCategory.for_name('ape', 'FR')
    belgium = OrganizationAtlasReferenceCategory.for_name('ape', 'BE')
    french_reference = OrganizationAtlasReference.objects.create(
        category=france, code='62.01Z', source='ref', country_code='FR',
    )
    belgian_reference = OrganizationAtlasReference.objects.create(
        category=belgium, code='62.01Z', source='ref', country_code='BE',
    )
    unknown_category = OrganizationAtlasReferenceCategory.for_name(
        'unknown_field', 'FR',
    )
    virtual = _virtual(
        denomination='Octolo', reference='1', source_field='siren',
        country_code='FR', backend='insee', address_json=None,
        ape='6201Z', unknown_field='unknown', data_source=None,
    )

    organization = create_organization(virtual)

    data = organization.to_organizationatlasdata.get(
        data_type__data_type='ape',
    )
    assert data.value == '62.01Z'
    assert list(data.reference.all()) == [french_reference]
    assert belgian_reference not in data.reference.all()
    unknown = organization.to_organizationatlasdata.get(
        data_type__data_type='unknown_field',
    )
    assert unknown.value == 'unknown'
    assert unknown.data_type.category == unknown_category
    assert not unknown.reference.exists()


@pytest.mark.django_db
def test_provider_refresh_replaces_only_the_previous_value_reference():
    category = OrganizationAtlasReferenceCategory.for_name('ape', 'FR')
    old = OrganizationAtlasReference.objects.create(
        category=category, code='old', source='ref', country_code='FR',
    )
    new = OrganizationAtlasReference.objects.create(
        category=category, code='new', source='ref', country_code='FR',
    )
    other = OrganizationAtlasReference.objects.create(
        category=OrganizationAtlasReferenceCategory.for_name('Other', 'FR'),
        code='manual', source='ref', country_code='FR',
    )
    virtual = _virtual(
        denomination='Octolo', reference='1', source_field='siren',
        country_code='FR', backend='insee', address_json=None,
        ape='old', data_source=None,
    )
    organization = create_organization(virtual)
    data = organization.to_organizationatlasdata.get(
        data_type__data_type='ape',
    )
    data.reference.add(other)
    data.valid_from = timezone.localdate()
    data.save(update_fields=['valid_from'])
    virtual.ape = 'new'

    refresh_organization(organization, virtual)

    data.refresh_from_db()
    assert data.value == 'new'
    assert set(data.reference.all()) == {new, other}
    assert old not in data.reference.all()
    virtual.ape = 'missing'

    refresh_organization(organization, virtual)

    data.refresh_from_db()
    assert data.value == 'missing'
    assert list(data.reference.all()) == [other]


@pytest.mark.django_db
def test_provider_uses_global_reference_when_country_category_is_absent():
    reference = OrganizationAtlasReference.objects.create(
        category=OrganizationAtlasReferenceCategory.for_name('activity', 'XG'),
        code='known', source='ref', country_code='XG',
    )
    virtual = _virtual(
        denomination='Octolo', reference='1', source_field='siren',
        country_code='BE', backend='provider', address_json=None,
        activity='known', data_source=None,
    )

    organization = create_organization(virtual)

    data = organization.to_organizationatlasdata.get(
        data_type__data_type='activity',
    )
    assert data.country_code == 'BE'
    assert data.data_type.category == reference.category
    assert list(data.reference.all()) == [reference]


@pytest.mark.django_db
def test_provider_history_links_references_to_historical_values():
    category = OrganizationAtlasReferenceCategory.for_name('ape', 'FR')
    reference = OrganizationAtlasReference.objects.create(
        category=category, code='62.01Z', source='ref', country_code='FR',
    )
    organization = OrganizationAtlasOrganization.objects.create(
        denomination='Octolo', code='1', source='insee', country_code='FR',
    )

    apply_organization_history(
        organization,
        [{
            'field': 'ape', 'value': '6201Z', 'country_code': 'FR',
            'valid_from': '2020-01-01', 'valid_to': '2021-01-01',
        }],
        source='insee',
    )

    data = organization.to_organizationatlasdata.get()
    assert data.value == '62.01Z'
    assert list(data.reference.all()) == [reference]


@pytest.mark.django_db
def test_refresh_does_not_create_history_for_a_format_only_change():
    organization = OrganizationAtlasOrganization.objects.create(
        denomination='Octolo', code='1', source='insee', country_code='FR',
    )
    OrganizationAtlasReference.objects.create(
        category=OrganizationAtlasReferenceCategory.for_name('ape', 'FR'),
        code='62.01Z', source='insee', country_code='FR',
    )
    data = OrganizationAtlasData.objects.create(
        organization=organization, source='insee', country_code='FR',
        data_type=OrganizationAtlasDataType.for_key('ape'), value='62.01Z',
        valid_from=date.today() - timedelta(days=10),
    )
    virtual = _virtual(
        denomination='Octolo', reference='1', source_field='siren',
        country_code='FR', backend='insee', address_json=None,
        ape='6201Z', data_source=None,
    )

    refresh_organization(organization, virtual)

    assert organization.to_organizationatlasdata.filter(
        data_type__data_type='ape',
    ).count() == 1
    data.refresh_from_db()
    assert data.value == '62.01Z'
    assert data.valid_to is None


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
    assert ape.value == "6201Z"
    current_ape = organization.to_organizationatlasdata.get(
        data_type__data_type="ape",
        source="INSEE SIRENE",
    )
    assert current_ape.value == "6311Z"
    capital = organization.to_organizationatlasdata.get(
        data_type__data_type="capital",
        source="INSEE SIRENE",
    )
    assert capital.value == "1000"
    assert capital.data_type.value_type == "str"
    trace = organization.to_organizationatlasdata.get(
        data_type__data_type="apitrace",
        reference__display_code="source",
    )
    assert trace.organization_id == organization.pk
    assert trace.data_type.value_type == "json"
    assert trace.value == '{"siren": "917432254"}'
    previous.refresh_from_db()
    assert previous.is_headquarters is True
    assert previous.valid_to is not None
    current = organization.to_organizationatlasaddress.get(
        is_headquarters=True,
        valid_to__isnull=True,
    )
    assert current.pk != previous.pk
    assert current.address["city"] == "Lyon"
    assert current.valid_from is not None


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


@pytest.mark.django_db
def test_refresh_historizes_changed_data_from_same_source():
    organization = OrganizationAtlasOrganization.objects.create(
        denomination="Octolo",
        code="917432254",
        source="INSEE",
        country_code="FR",
    )
    previous = OrganizationAtlasData.objects.create(
        organization=organization,
        source="INSEE",
        country_code="FR",
        data_type=OrganizationAtlasDataType.for_key("ape"),
        value="6201Z",
        valid_from=date.today() - timedelta(days=30),
    )
    virtual = _virtual(
        denomination="Octolo",
        reference="917432254",
        source_field="siren",
        country_code="FR",
        backend="INSEE",
        ape="6311Z",
    )

    refresh_organization(organization, virtual)

    previous.refresh_from_db()
    assert previous.valid_to == date.today() - timedelta(days=1)
    current = organization.to_organizationatlasdata.get(
        source="INSEE",
        country_code="FR",
        data_type__data_type="ape",
        valid_to__isnull=True,
    )
    assert current.value == "6311Z"
    assert current.valid_from == date.today()
