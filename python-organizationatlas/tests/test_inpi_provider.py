"""INPI provider API path tests."""

from unittest.mock import MagicMock, patch

import pytest
from requests import HTTPError

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
        ) as detail:
            results = provider.search_organization("octolo")

        assert results == [{"siren": "917432254"}]
        detail.assert_not_called()
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
        assert normalized["registry_type"] == "RNCS"
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

    @patch("organizationatlas.providers.europe.france.inpi.requests.post")
    @patch("organizationatlas.providers.europe.france.inpi.requests.get")
    def test_expired_token_is_refreshed_once(self, mock_get, mock_post):
        unauthorized = MagicMock(status_code=401)
        success = MagicMock(status_code=200)
        success.json.return_value = {"siren": "917432254"}
        mock_get.side_effect = [unauthorized, success]

        login = MagicMock(status_code=200)
        login.json.return_value = {"token": "fresh-token"}
        mock_post.return_value = login

        provider = InpiProvider()
        provider._token = "expired-token"
        provider._get_config_or_env = MagicMock(
            side_effect=lambda key: {
                "API_USERNAME": "user",
                "API_PASSWORD": "password",
                "SSO_URL": "https://example.test/login",
            }[key]
        )

        assert provider._call_api("https://example.test/company") == {
            "siren": "917432254"
        }
        assert mock_get.call_count == 2
        assert mock_get.call_args_list[0].kwargs["headers"]["Authorization"] == "Bearer expired-token"
        assert mock_get.call_args_list[1].kwargs["headers"]["Authorization"] == "Bearer fresh-token"
        mock_post.assert_called_once()

    @patch("organizationatlas.providers.europe.france.inpi.requests.post")
    def test_authentication_errors_are_propagated(self, mock_post):
        mock_post.return_value.raise_for_status.side_effect = HTTPError("invalid credentials")
        provider = InpiProvider()
        provider._get_config_or_env = MagicMock(
            side_effect=lambda key: {
                "API_USERNAME": "user",
                "API_PASSWORD": "bad-password",
                "SSO_URL": "https://example.test/login",
            }[key]
        )

        with pytest.raises(HTTPError, match="invalid credentials"):
            provider._get_token()

    @patch.object(InpiProvider, "_get_token", side_effect=["expired", "fresh"])
    @patch("organizationatlas.providers.europe.france.inpi.requests.get")
    def test_second_unauthorized_response_is_propagated(self, mock_get, _mock_token):
        unauthorized = MagicMock(status_code=401)
        unauthorized.raise_for_status.side_effect = HTTPError("unauthorized")
        mock_get.return_value = unauthorized

        with pytest.raises(HTTPError, match="unauthorized"):
            InpiProvider()._call_api("https://example.test/company")

        assert mock_get.call_count == 2
