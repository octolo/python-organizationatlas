from datetime import date

import pytest
from django.core.exceptions import ValidationError

from django_organizationatlas.models import (
    OrganizationAtlasData,
    OrganizationAtlasDataType,
    OrganizationAtlasOrganization,
)


@pytest.fixture
def organization(db):
    return OrganizationAtlasOrganization.objects.create(
        denomination="Octolo",
        code="917432254",
        source="insee",
        country_code="FR",
    )


@pytest.mark.parametrize(
    ("value_type", "value", "expected"),
    [
        ("str", "text", "text"),
        ("int", "42", 42),
        ("float", "4.2", 4.2),
        ("bool", "yes", True),
        ("bool", "off", False),
        ("date", "2026-10-29", date(2026, 10, 29)),
        ("json", '{"active": true}', {"active": True}),
    ],
)
@pytest.mark.django_db
def test_typed_value(organization, value_type, value, expected):
    data = OrganizationAtlasData(
        organization=organization,
        data_type=OrganizationAtlasDataType.objects.create(
            data_type=f"{value_type}-{value}",
            value_type=value_type,
        ),
        value=value,
    )

    assert data.typed_value == expected


@pytest.mark.parametrize(
    ("value_type", "value"),
    [
        ("int", "four"),
        ("float", "four"),
        ("bool", "perhaps"),
        ("date", "29/10/2026"),
        ("json", "{invalid"),
    ],
)
@pytest.mark.django_db
def test_clean_rejects_value_that_does_not_match_type(
    organization,
    value_type,
    value,
):
    data = OrganizationAtlasData(
        organization=organization,
        data_type=OrganizationAtlasDataType.objects.create(
            data_type=f"invalid-{value_type}",
            value_type=value_type,
        ),
        value=value,
    )

    with pytest.raises(ValidationError) as exc:
        data.clean()

    assert "value" in exc.value.message_dict


@pytest.mark.django_db
def test_data_type_rejects_conflicting_value_type():
    OrganizationAtlasDataType.for_key("employees", "int")

    with pytest.raises(ValueError, match="already uses value type"):
        OrganizationAtlasDataType.for_key("employees", "str")
