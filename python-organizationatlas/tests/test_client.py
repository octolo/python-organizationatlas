"""Tests for organizationatlas helpers and providers."""

import pytest

from organizationatlas import (
    ORGANIZATIONATLAS_GET_COMPANY_DOCUMENTS_FIELDS,
    ORGANIZATIONATLAS_GET_COMPANY_EVENTS_FIELDS,
    ORGANIZATIONATLAS_GET_COMPANY_OFFICERS_FIELDS,
    ORGANIZATIONATLAS_GET_ULTIMATE_BENEFICIAL_OWNERS_FIELDS,
    ORGANIZATIONATLAS_GET_REFERENTIEL_FIELDS,
    ORGANIZATIONATLAS_SEARCH_COMPANY_FIELDS,
)
from organizationatlas.providers import OrganizationAtlasProvider
from organizationatlas.providers.europe.france import OrganizationAtlasFranceProvider


class TestFieldSchemas:
    def test_search_organization_fields_has_required_keys(self):
        required = {"denomination", "reference", "organizationatlas_id", "backend_name"}
        assert required.issubset(ORGANIZATIONATLAS_SEARCH_COMPANY_FIELDS)

    def test_list_response_fields_have_organizationatlas_id(self):
        for schema in [
            ORGANIZATIONATLAS_GET_COMPANY_DOCUMENTS_FIELDS,
            ORGANIZATIONATLAS_GET_COMPANY_EVENTS_FIELDS,
            ORGANIZATIONATLAS_GET_COMPANY_OFFICERS_FIELDS,
            ORGANIZATIONATLAS_GET_ULTIMATE_BENEFICIAL_OWNERS_FIELDS,
        ]:
            assert "organizationatlas_id" in schema

    def test_referentiel_fields(self):
        expected = {"category", "code", "description", "characteristics", "priority", "usage_type"}
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
        assert provider.is_rna("W12345678")
        assert provider.is_rna("w12345678")
        assert not provider.is_rna("123456789")
        assert not provider.is_rna("")

    def test_detect_code_type(self, provider):
        assert provider._detect_code_type("123456789") == "siren"
        assert provider._detect_code_type("12345678901234") == "siret"
        assert provider._detect_code_type("W12345678") == "rna"
        assert provider._detect_code_type("invalid") is None

    def test_format_siren(self, provider):
        assert provider._format_siren("123 456 789") == "123456789"
        assert provider._format_siren("123-456-789") == "123456789"

    def test_validate_siren(self, provider):
        assert provider._validate_siren("123456789")
        assert not provider._validate_siren("12345678")
