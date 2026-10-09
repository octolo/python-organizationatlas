"""INPI provider API path tests."""

from unittest.mock import MagicMock, patch

from organizationatlas.providers.europe.france.inpi import InpiProvider


class TestInpiProviderApiPaths:
    @patch.object(InpiProvider, "_get_token", return_value="token")
    @patch("organizationatlas.providers.europe.france.inpi.requests.get")
    def test_search_uses_companies_endpoint(self, mock_get, _mock_token):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"companies": [{"siren": "917432254"}]},
        )
        mock_get.return_value.raise_for_status = MagicMock()

        provider = InpiProvider()
        with patch.object(
            provider,
            "search_organization_by_reference",
            return_value={
                "siren": "917432254",
                "content": {
                    "personneMorale": {
                        "identite": {"entreprise": {"denomination": "OCTOLO"}},
                    },
                },
            },
        ):
            results = provider.search_organization("octolo")

        assert len(results) == 1
        mock_get.assert_called_once()
        url = mock_get.call_args[0][0]
        params = mock_get.call_args[1]["params"]
        assert url.endswith("/api/companies")
        assert params["companyName"] == "octolo"
        assert "organizationName" not in params

    @patch.object(InpiProvider, "_get_token", return_value="token")
    @patch("organizationatlas.providers.europe.france.inpi.requests.get")
    def test_search_by_reference_uses_companies_siren(self, mock_get, _mock_token):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"siren": "917432254"},
        )
        mock_get.return_value.raise_for_status = MagicMock()

        provider = InpiProvider()
        result = provider.search_organization_by_reference("917432254")

        assert result == {"siren": "917432254"}
        mock_get.assert_called_once()
        assert mock_get.call_args[0][0].endswith("/api/companies/917432254")

    def test_normalize_denomination_from_content(self):
        provider = InpiProvider()
        data = {
            "siren": "917432254",
            "content": {
                "personneMorale": {
                    "identite": {"entreprise": {"denomination": "OCTOLO"}},
                },
            },
        }
        normalized = provider.normalize(data, config=provider.services_cfg["search_organization"])
        assert normalized["denomination"] == "OCTOLO"
        assert normalized["reference"] == "917432254"

    def test_normalize_denomination_personne_physique_autres_etablissements(self):
        provider = InpiProvider()
        data = {
            "siren": "977793561",
            "content": {
                "personnePhysique": {
                    "identite": {
                        "entreprise": None,
                        "entrepreneur": {
                            "descriptionPersonne": {
                                "nom": "ZLAIJI EL BAZAZI",
                                "prenoms": ["MOHAMMED"],
                            },
                        },
                    },
                    "etablissementPrincipal": None,
                    "autresEtablissements": [
                        {
                            "descriptionEtablissement": {
                                "indicateurEtablissementPrincipal": True,
                                "nomCommercial": "DOCTOLOC",
                            },
                        },
                    ],
                },
            },
        }
        normalized = provider.normalize(data, config=provider.services_cfg["search_organization"])
        assert normalized["denomination"] == "DOCTOLOC"
        assert normalized["reference"] == "977793561"

    def test_normalize_address_from_formality_payload(self):
        provider = InpiProvider()
        data = {
            "siren": "917432254",
            "formality": {
                "siren": "917432254",
                "content": {
                    "natureCreation": {"dateCreation": "2022-07-12", "formeJuridique": "5710"},
                    "registreAnterieur": {
                        "rncs": {"estPresent": True, "dateImmatriculation": "2022-07-12T00:00:00+02:00"},
                    },
                    "personneMorale": {
                        "adresseEntreprise": {
                            "adresse": {
                                "pays": "FRANCE",
                                "codePays": "FRA",
                                "codePostal": "92400",
                                "commune": "Courbevoie",
                                "typeVoie": "BD",
                                "voie": " 295 Boulevard Saint-Denis",
                                "numVoie": "295",
                            },
                        },
                        "etablissementPrincipal": {
                            "descriptionEtablissement": {"indicateurEtablissementPrincipal": True},
                            "adresse": {
                                "pays": "FRANCE",
                                "codePays": "FRA",
                                "codePostal": "92400",
                                "commune": "Courbevoie",
                                "typeVoie": "BD",
                                "voie": " 295 Boulevard Saint-Denis",
                                "numVoie": "295",
                            },
                        },
                        "identite": {
                            "entreprise": {
                                "denomination": "OCTOLO",
                                "siren": "917432254",
                                "formeJuridique": "5710",
                                "codeApe": "6201Z",
                            },
                        },
                        "observations": {"rcs": {"rcs": {"nomGreffe": "Paris"}}},
                    },
                },
            },
        }
        normalized = provider.normalize(data, config=provider.services_cfg["search_organization"])
        assert normalized["address"] == "295 Boulevard Saint-Denis, 92400, Courbevoie"
        assert normalized["address_json"] == {
            "address_line1": "295 Boulevard Saint-Denis",
            "postal_code": "92400",
            "city": "Courbevoie",
            "country": "FRANCE",
            "country_code": "FR",
        }
        assert normalized["ape"] == "6201Z"
        assert normalized["ape_noun"] is None
        assert normalized["legalform"] == "5710"
        assert normalized["category"] is None
        assert normalized["slice_effective"] is None
        assert normalized["registry_type"] is None
        assert normalized["registry_authority"] == "Paris"
        assert normalized["since"] == "2022-07-12"

    def test_normalize_address_keeps_separate_street_parts(self):
        provider = InpiProvider()
        data = {
            "content": {
                "personneMorale": {
                    "etablissementPrincipal": {
                        "adresse": {
                            "numVoie": "10",
                            "typeVoie": "RUE",
                            "voie": "DE RIVOLI",
                            "codePostal": "75001",
                            "commune": "Paris",
                        },
                    },
                },
            },
        }
        normalized = provider.normalize(data, config=provider.services_cfg["search_organization"])
        assert normalized["address_json"]["address_line1"] == "10 RUE DE RIVOLI"
