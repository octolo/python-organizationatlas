from organizationatlas.providers.europe.france.entdatagouv import EntdatagouvProvider
from organizationatlas.providers.europe.france.huwise import HuwiseProvider
from organizationatlas.providers.europe.france.insee import InseeProvider


def _normalize(provider, data):
    return provider.normalize(data, config=provider.services_cfg["search_organization"])


def test_insee_company_fields():
    normalized = _normalize(InseeProvider(), {
        "siren": "917432254",
        "uniteLegale": {
            "activitePrincipaleUniteLegale": "62.01Z",
            "nomenclatureActivitePrincipaleUniteLegale": "NAFRev2",
            "categorieJuridiqueUniteLegale": "5710",
            "dateCreationUniteLegale": "2022-07-01",
        },
    })
    assert normalized["ape"] == "6201Z"
    assert normalized["ape_noun"] == "NAFRev2"
    assert normalized["legalform"] == "5710"
    assert normalized["since"] == "2022-07-01"
    assert normalized["registry_type"] is None


def test_entdatagouv_uses_siren_not_siret_as_reference():
    normalized = _normalize(EntdatagouvProvider(), {
        "siren": "917432254",
        "nom_complet": "OCTOLO",
        "nom_raison_sociale": "OCTOLO",
        "nature_juridique": "5710",
        "activite_principale": "62.01Z",
        "date_creation": "2022-07-01",
        "siege": {
            "activite_principale": "62.01Z",
            "siret": "91743225400014",
            "numero_voie": "295",
            "type_voie": "BOULEVARD",
            "libelle_voie": "SAINT-DENIS",
            "code_postal": "92400",
            "libelle_commune": "COURBEVOIE",
            "date_creation": "2022-07-01",
        },
        "complements": {"identifiant_association": None, "est_association": False},
    })
    assert normalized["siren"] == "917432254"
    assert normalized["siret"] == "91743225400014"
    assert normalized["reference"] == "917432254"
    assert normalized["source_field"] == "siren"
    assert normalized["denomination"] == "OCTOLO"
    assert normalized["ape"] == "6201Z"
    assert normalized["legalform"] == "5710"
    assert normalized["since"] == "2022-07-01"
    assert normalized["address"] == "295 BOULEVARD SAINT-DENIS, 92400, COURBEVOIE"


def test_entdatagouv_company_fields():
    normalized = _normalize(EntdatagouvProvider(), {
        "siren": "917432254",
        "nature_juridique": "5710",
        "date_creation": "2022-07-01",
        "siege": {"activite_principale": "62.01Z"},
    })
    assert normalized["ape"] == "6201Z"
    assert normalized["ape_noun"] is None
    assert normalized["legalform"] == "5710"
    assert normalized["since"] == "2022-07-01"
    assert normalized["registry_type"] is None


def test_huwise_company_fields():
    normalized = _normalize(HuwiseProvider(), {
        "siren": "917432254",
        "activiteprincipaleunitelegale": "6201Z",
        "nomenclatureactiviteprincipaleunitelegale": "NAFRev2",
        "categoriejuridiqueunitelegale": "5710",
        "datecreationunitelegale": "2022-07-01",
    })
    assert normalized["ape"] == "6201Z"
    assert normalized["ape_noun"] == "NAFRev2"
    assert normalized["legalform"] == "5710"
    assert normalized["since"] == "2022-07-01"
    assert normalized["registry_type"] is None
