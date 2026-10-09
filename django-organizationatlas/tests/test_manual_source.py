from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.test import override_settings

from django_organizationatlas.models import (
    OrganizationAtlasData,
    OrganizationAtlasDataType,
    OrganizationAtlasOrganization,
)
from django_organizationatlas.models.source import USER_COUNTRY_CODE


@pytest.mark.django_db
def test_manual_data_records_user_id_and_user_country_code():
    user = User.objects.create(username="ada")
    organization = OrganizationAtlasOrganization.objects.create(
        denomination="Octolo",
        code="917432254",
        source="INSEE",
        country_code="FR",
    )
    with patch("django_organizationatlas.models.source.get_current_user", return_value=user):
        row = OrganizationAtlasData.objects.create(
            organization=organization,
            data_type=OrganizationAtlasDataType.for_key("note"),
            value="hello",
        )
    assert row.source == str(user.pk)
    assert row.country_code == USER_COUNTRY_CODE
    assert row.source_label() == f"{USER_COUNTRY_CODE}/{user.pk}"


@pytest.mark.django_db
def test_provider_source_is_left_unchanged():
    user = User.objects.create(username="ada")
    organization = OrganizationAtlasOrganization.objects.create(
        denomination="Octolo",
        code="917432254",
    )
    with patch("django_organizationatlas.models.source.get_current_user", return_value=user):
        row = OrganizationAtlasData.objects.create(
            organization=organization,
            data_type=OrganizationAtlasDataType.for_key("siren"),
            value="917432254",
            source="data.gouv.fr",
            country_code="FR",
        )
    assert row.source == "data.gouv.fr"
    assert row.country_code == "FR"
    assert row.source_label() == "FR/data.gouv.fr"


@pytest.mark.django_db
@override_settings(ORGANIZATIONATLAS_USER_SOURCE="username")
def test_manual_source_uses_configured_user_attribute():
    user = User.objects.create(username="ada")
    organization = OrganizationAtlasOrganization.objects.create(
        denomination="Octolo",
        code="917432254",
    )
    with patch("django_organizationatlas.models.source.get_current_user", return_value=user):
        row = OrganizationAtlasData.objects.create(
            organization=organization,
            data_type=OrganizationAtlasDataType.for_key("note"),
            value="hello",
        )
    assert row.source == "ada"
    assert row.country_code == USER_COUNTRY_CODE
