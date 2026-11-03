from datetime import date

import pytest

from django_organizationatlas.models import (
    OrganizationAtlasData,
    OrganizationAtlasDataType,
    OrganizationAtlasOrganization,
    OrganizationAtlasReference,
    OrganizationAtlasReferenceCategory,
)


def _organization():
    return OrganizationAtlasOrganization.objects.create(
        denomination="Octolo",
        code="917432254",
        source="organizationatlas",
        country_code="FR",
    )


def _majority():
    category = OrganizationAtlasReferenceCategory.for_name("DECISIONS", "FR")
    return OrganizationAtlasReference.objects.create(
        category=category,
        code="ORDINARY_MAJORITY",
        description="Majorité des décisions ordinaires",
        default_value="50%",
        country_code="FR",
        source="organizationatlas",
    )


@pytest.mark.django_db
def test_rule_value_uses_the_reference_default():
    organization = _organization()
    _majority()

    assert organization.rule_value("fr/DECISIONS", "ORDINARY_MAJORITY") == "50%"


@pytest.mark.django_db
def test_rule_value_prefers_current_data_linked_to_the_reference():
    organization = _organization()
    reference = _majority()
    data = OrganizationAtlasData.objects.create(
        organization=organization,
        data_type=OrganizationAtlasDataType.for_key("company_rule"),
        value="66%",
        source="organizationatlas",
        country_code="FR",
    )
    data.reference.add(reference)

    assert organization.rule_value("FR/DECISIONS", "ORDINARY_MAJORITY") == "66%"


@pytest.mark.django_db
def test_rule_value_ignores_closed_data():
    organization = _organization()
    reference = _majority()
    data = OrganizationAtlasData.objects.create(
        organization=organization,
        data_type=OrganizationAtlasDataType.for_key("company_rule"),
        value="66%",
        source="organizationatlas",
        country_code="FR",
        valid_to=date(2020, 1, 1),
    )
    data.reference.add(reference)

    assert organization.rule_value("fr/DECISIONS", "ORDINARY_MAJORITY") == "50%"


@pytest.mark.django_db
def test_rule_value_returns_empty_when_the_reference_is_unknown():
    organization = _organization()

    assert organization.rule_value("fr/DECISIONS", "QUORUM") == ""
