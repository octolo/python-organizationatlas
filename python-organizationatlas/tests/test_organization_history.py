from unittest.mock import MagicMock

from organizationatlas.providers import OrganizationAtlasProvider
from organizationatlas.providers.europe.france.entdatagouv import EntdatagouvProvider
from organizationatlas.providers.europe.france.huwise import HuwiseProvider
from organizationatlas.providers.europe.france.inpi import InpiProvider
from organizationatlas.providers.europe.france.insee import (
    _LEGAL_UNIT_HISTORY_FIELDS,
    InseeProvider,
    _history_from_periods,
)

_PERIODS = [
    {
        "dateDebut": "2020-01-01",
        "dateFin": None,
        "denominationUniteLegale": "NEW",
        "changementDenominationUniteLegale": True,
        "activitePrincipaleUniteLegale": "62.01Z",
        "categorieJuridiqueUniteLegale": "5710",
        "nicSiegeUniteLegale": "00014",
        "nomUniteLegale": None,
    },
    {
        "dateDebut": "2015-06-01",
        "dateFin": "2019-12-31",
        "denominationUniteLegale": "OLD",
        "activitePrincipaleUniteLegale": "62.01Z",
        "categorieJuridiqueUniteLegale": "5499",
        "nicSiegeUniteLegale": "00014",
    },
    {
        "dateDebut": "2010-01-01",
        "dateFin": "2015-05-31",
        "denominationUniteLegale": "OLD",
        "activitePrincipaleUniteLegale": "70.22Z",
        "categorieJuridiqueUniteLegale": "5499",
        "nicSiegeUniteLegale": "[ND]",
    },
]


def _rows(**kwargs):
    return _history_from_periods(_PERIODS, _LEGAL_UNIT_HISTORY_FIELDS, siren="917432254", siret=None, scope="legal_unit")


def _by_field(field):
    return [row for row in _rows() if row["field"] == field]


def test_history_service_is_declared():
    service = OrganizationAtlasProvider._default_services_cfg["get_organization_history"]
    assert "field" in service["fields"]
    assert "valid_from" in service["fields"]
    assert InseeProvider().is_service_implemented("get_organization_history")
    assert not EntdatagouvProvider().is_service_implemented("get_organization_history")
    assert not HuwiseProvider().is_service_implemented("get_organization_history")
    assert not InpiProvider().is_service_implemented("get_organization_history")


def test_history_collapses_values_that_do_not_change():
    denominations = _by_field("denomination")
    assert [(row["value"], row["valid_from"], row["valid_to"]) for row in denominations] == [
        ("OLD", "2010-01-01", "2019-12-31"),
        ("NEW", "2020-01-01", None),
    ]
    apes = _by_field("ape")
    assert [(row["value"], row["valid_from"], row["valid_to"]) for row in apes] == [
        ("70.22Z", "2010-01-01", "2015-05-31"),
        ("62.01Z", "2015-06-01", None),
    ]
    assert _by_field("legalform")[0]["value"] == "5499"
    assert _by_field("legalform")[0]["valid_to"] == "2019-12-31"
    assert _by_field("headquarters_nic") == [
        {
            "field": "headquarters_nic",
            "value": "00014",
            "valid_from": "2015-06-01",
            "valid_to": None,
            "scope": "legal_unit",
            "siren": "917432254",
            "siret": None,
            "reference": "917432254",
        }
    ]


def test_history_reopens_a_value_after_a_gap():
    periods = [
        {"dateDebut": "2010-01-01", "dateFin": "2012-01-01", "denominationUniteLegale": "OCTOLO"},
        {"dateDebut": "2012-01-02", "dateFin": "2014-01-01", "denominationUniteLegale": None},
        {"dateDebut": "2014-01-02", "dateFin": None, "denominationUniteLegale": "OCTOLO"},
    ]
    rows = _history_from_periods(
        periods,
        {"denominationUniteLegale": "denomination"},
        siren="917432254",
        siret=None,
        scope="legal_unit",
    )
    assert [(row["valid_from"], row["valid_to"]) for row in rows] == [
        ("2010-01-01", "2012-01-01"),
        ("2014-01-02", None),
    ]


def test_get_organization_history_reads_legal_unit_and_current_headquarters():
    provider = InseeProvider()
    fetched = []

    def fake_fetch(path):
        fetched.append(path)
        if path.startswith("siren/"):
            return {"uniteLegale": {"siren": "917432254", "periodesUniteLegale": _PERIODS}}
        return {
            "etablissement": {
                "periodesEtablissement": [
                    {
                        "dateDebut": "2015-06-01",
                        "dateFin": None,
                        "denominationUsuelleEtablissement": "OCTOLO",
                        "etatAdministratifEtablissement": "A",
                    }
                ]
            }
        }

    provider._fetch_sirene = fake_fetch
    rows = provider.get_organization_history("917 432 254")

    assert fetched == ["siren/917432254", "siret/91743225400014"]
    usual = next(row for row in rows if row["field"] == "establishment_usual_denomination")
    assert usual["value"] == "OCTOLO"
    assert usual["siret"] == "91743225400014"
    assert usual["scope"] == "establishment"
    assert usual["valid_to"] is None


def test_siret_history_uses_that_establishment():
    provider = InseeProvider()
    fetched = []

    def fake_fetch(path):
        fetched.append(path)
        if path.startswith("siren/"):
            return {"uniteLegale": {"siren": "917432254", "periodesUniteLegale": _PERIODS}}
        return {"etablissement": {"periodesEtablissement": []}}

    provider._fetch_sirene = fake_fetch
    provider.get_organization_history("91743225400099")
    assert fetched == ["siren/917432254", "siret/91743225400099"]


def test_unknown_siren_returns_no_history():
    provider = InseeProvider()
    provider._fetch_sirene = lambda path: None
    assert provider.get_organization_history("917432254") == []


def test_invalid_code_does_not_call_sirene():
    provider = InseeProvider()
    provider._fetch_sirene = lambda path: (_ for _ in ()).throw(AssertionError(path))
    assert provider.get_organization_history("not-a-code") == []


def test_identifier_search_returns_empty_list_when_reference_is_not_found():
    provider = InseeProvider()
    provider._call_api = MagicMock(return_value=[])

    assert provider.search_organization("917432254") == []


def test_insee_search_escapes_quoted_phrase():
    provider = InseeProvider()
    provider._call_api = MagicMock(return_value=[])

    provider.search_organization('ACME" OR siren:*\\')

    query = provider._call_api.call_args.args[0]
    assert query == 'denominationUniteLegale:"ACME\\" OR siren:*\\\\"'


def test_rna_history_lookup_requires_an_active_legal_unit():
    provider = InseeProvider()
    provider._call_api = MagicMock(
        return_value=[{"siren": "917432254", "siret": "91743225400014"}]
    )

    assert provider._identifiers_for_history("W123456789") == (
        "917432254",
        "91743225400014",
    )
    query = provider._call_api.call_args.args[0]
    assert "etatAdministratifUniteLegale:A" in query


def test_normalize_history_row():
    provider = InseeProvider()
    normalized = provider.normalize(
        {
            "field": "denomination",
            "value": "OLD",
            "valid_from": "2010-01-01",
            "valid_to": "2019-12-31",
            "scope": "legal_unit",
            "siren": "917432254",
            "siret": None,
            "reference": "917432254",
        },
        config=provider.services_cfg["get_organization_history"],
    )
    assert normalized["field"] == "denomination"
    assert normalized["value"] == "OLD"
    assert normalized["valid_to"] == "2019-12-31"
    assert normalized["siren"] == "917432254"
    assert normalized["country_code"] == "FR"
    assert normalized["organizationatlas_id"] == "insee_917432254"
