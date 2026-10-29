"""Tests for organizationatlas helpers and providers."""

from unittest.mock import MagicMock

import pytest

from organizationatlas import (
    ORGANIZATIONATLAS_GET_COMPANY_DOCUMENTS_FIELDS,
    ORGANIZATIONATLAS_GET_COMPANY_EVENTS_FIELDS,
    ORGANIZATIONATLAS_GET_COMPANY_OFFICERS_FIELDS,
    ORGANIZATIONATLAS_GET_ULTIMATE_BENEFICIAL_OWNERS_FIELDS,
    ORGANIZATIONATLAS_GET_REFERENTIEL_FIELDS,
    ORGANIZATIONATLAS_SEARCH_COMPANY_FIELDS,
)
from organizationatlas.providers import get_search_organization_fields
from organizationatlas.providers.europe.france import OrganizationAtlasFranceProvider
from organizationatlas.providers.europe.france.entdatagouv import EntdatagouvProvider


class TestFieldSchemas:
    def test_search_organization_fields_has_required_keys(self):
        required = {"denomination", "reference", "organizationatlas_id", "backend_name"}
        assert required.issubset(ORGANIZATIONATLAS_SEARCH_COMPANY_FIELDS)

    def test_country_fields_declared_on_country_provider(self):
        france_fields = OrganizationAtlasFranceProvider.services_cfg["search_organization"]["fields"]
        assert "siren" not in ORGANIZATIONATLAS_SEARCH_COMPANY_FIELDS
        assert {"siren", "denomination"}.issubset(france_fields)
        assert {"siren", "denomination"}.issubset(get_search_organization_fields())

    def test_list_response_fields_have_organizationatlas_id(self):
        for schema in [
            ORGANIZATIONATLAS_GET_COMPANY_DOCUMENTS_FIELDS,
            ORGANIZATIONATLAS_GET_COMPANY_EVENTS_FIELDS,
            ORGANIZATIONATLAS_GET_COMPANY_OFFICERS_FIELDS,
            ORGANIZATIONATLAS_GET_ULTIMATE_BENEFICIAL_OWNERS_FIELDS,
        ]:
            assert "organizationatlas_id" in schema

    def test_referentiel_fields(self):
        expected = {"category", "code", "description", "characteristics", "priority"}
        assert expected == set(ORGANIZATIONATLAS_GET_REFERENTIEL_FIELDS)


class TestFranceProviderValidation:
    @pytest.fixture
    def provider(self):
        class ConcreteProvider(OrganizationAtlasFranceProvider):
            name = "test"
            display_name = "Test"
            abstract = False
        return ConcreteProvider()

    def test_is_siren(self, provider):
        assert provider.is_siren("123456789")
        assert not provider.is_siren("12345678")
        assert not provider.is_siren("12345678901234")
        assert not provider.is_siren("")
        assert not provider.is_siren(None)

    def test_is_siret(self, provider):
        assert provider.is_siret("12345678901234")
        assert not provider.is_siret("123456789")
        assert not provider.is_siret("")

    def test_is_rna(self, provider):
        assert provider.is_rna("W123456789")
        assert provider.is_rna("w123456789")
        assert not provider.is_rna("W")
        assert not provider.is_rna("W123")
        assert not provider.is_rna("W12345678")
        assert not provider.is_rna("W1234567890")
        assert not provider.is_rna("123456789")
        assert not provider.is_rna("")

    def test_detect_code_type(self, provider):
        assert provider._detect_code_type("123456789") == "siren"
        assert provider._detect_code_type("12345678901234") == "siret"
        assert provider._detect_code_type("W123456789") == "rna"
        assert provider._detect_code_type("invalid") is None

    def test_format_siren(self, provider):
        assert provider._format_siren("123 456 789") == "123456789"
        assert provider._format_siren("123-456-789") == "123456789"
        assert provider._format_siren("1234567890") == "1234567890"

    def test_validate_siren(self, provider):
        assert provider._validate_siren("123456789")
        assert not provider._validate_siren("12345678")


def test_entdatagouv_rna_lookup_uses_search_endpoint():
    provider = EntdatagouvProvider()
    provider._call_api = MagicMock(
        return_value={"results": [{"siren": "917432254"}]}
    )

    assert provider.search_organization_by_reference("W123456789") == {
        "siren": "917432254"
    }
    provider._call_api.assert_called_once_with(
        "https://recherche-entreprises.api.gouv.fr/search?q=W123456789"
    )


def test_normalized_id_requires_reference():
    provider = EntdatagouvProvider()

    assert provider.get_insert_normalized_organizationatlas_id(
        {},
        {"reference": None},
        {},
    ) is None
