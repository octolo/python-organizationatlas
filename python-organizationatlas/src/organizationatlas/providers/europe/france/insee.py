import re
from typing import Any, cast
from urllib.parse import quote, urlencode

import requests

from . import OrganizationAtlasFranceProvider


class InseeProvider(OrganizationAtlasFranceProvider):
    name = "insee"
    display_name = "INSEE SIRENE"
    description = "Official French organization registry (SIRENE database)"
    required_packages = ["requests"]
    config_keys = ["API_KEY"]
    documentation_url = "https://portail-api.insee.fr/"
    site_url = "https://www.insee.fr"
    status_url = "https://api.insee.fr/status"
    priority = 4

    fields_associations = {
        "denomination": "uniteLegale.denominationUniteLegale",
        "reference": ("siren", "siret", "uniteLegale.identifiantAssociationUniteLegale"),
        "siren": "siren",
        "siret": "siret",
        "rna": "uniteLegale.identifiantAssociationUniteLegale",
        "ape": "uniteLegale.activitePrincipaleUniteLegale",
        "ape_noun": "uniteLegale.nomenclatureActivitePrincipaleUniteLegale",
        "legalform": "uniteLegale.categorieJuridiqueUniteLegale",
        "slice_effective": "uniteLegale.trancheEffectifsUniteLegale",
        "since": "uniteLegale.dateCreationUniteLegale",
        "address": (
            "adresseEtablissement.numeroVoieEtablissement",
            "adresseEtablissement.typeVoieEtablissement",
            "adresseEtablissement.libelleVoieEtablissement",
            "adresseEtablissement.codePostalEtablissement",
            "adresseEtablissement.libelleCommuneEtablissement",
        ),
    }

    def _get_address_parts(self, data: dict[str, Any]) -> tuple:
        return (
            self._get_nested_value(data, "adresseEtablissement.numeroVoieEtablissement"),
            self._get_nested_value(data, "adresseEtablissement.typeVoieEtablissement"),
            self._get_nested_value(data, "adresseEtablissement.libelleVoieEtablissement"),
            self._get_nested_value(data, "adresseEtablissement.codePostalEtablissement"),
            self._get_nested_value(data, "adresseEtablissement.libelleCommuneEtablissement"),
        )

    def get_normalize_address_json(self, data: dict[str, Any]) -> dict[str, Any] | None:
        return self._build_address_json(*self._get_address_parts(data))

    def get_normalize_address(self, data: dict[str, Any]) -> str | None:
        numero, type_voie, libelle, code_postal, commune = self._get_address_parts(data)
        country = self._get_nested_value(
            data, "adresseEtablissement.libellePaysEtablissement", self.geo_country
        )
        return self._build_address_str(numero, type_voie, libelle, code_postal, commune, country)

    def _call_api(self, query: str, endpoint: str = "siret") -> list[dict[str, Any]]:
        api_key = self._get_config_or_env("API_KEY")
        if not api_key:
            raise ValueError("INSEE API_KEY is required but not configured")
        query_params = {
            "q": query,
            "nombre": 20,
            "debut": 0,
            "masquerValeursNulles": "true",
        }
        query_string = urlencode(
            query_params,
            quote_via=lambda s, safe="", encoding=None, errors=None: quote(s, safe="+", encoding=encoding, errors=errors),
        )
        url = f"https://api.insee.fr/api-sirene/3.11/{endpoint}?{query_string}"
        headers = {"Accept": "application/json", "X-INSEE-Api-Key-Integration": api_key}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        if "etablissements" in data:
            return cast("list[dict[str, Any]]", data["etablissements"])
        if "unitesLegales" in data:
            return cast("list[dict[str, Any]]", data["unitesLegales"])
        return []

    def search_organization(self, query: str, raw: bool = False, **kwargs: Any) -> list[dict[str, Any]]:
        if not query:
            return []
        if self.is_siren(query) or self.is_siret(query) or self.is_rna(query):
            return [self.search_organization_by_reference(query, by_pass=True)]
        query_clean = query.replace("+", " ").strip()
        return self._call_api(f'denominationUniteLegale:"{query_clean}"', endpoint="siret")

    def search_organization_by_reference(self, code: str, raw: bool = False, **kwargs: Any) -> dict[str, Any] | None:
        if not code:
            return None
        code_type = self._detect_code_type(code)
        if not code_type:
            return None
        code_clean = re.sub(r"[\s-]", "", code)
        if code_type == "siren":
            query_str = f"siren:{code_clean}+AND+etatAdministratifUniteLegale:A+AND+etablissementSiege:true"
        elif code_type == "siret":
            query_str = f"siret:{code_clean}+AND+etatAdministratifUniteLegale:A+AND+etablissementSiege:true"
        else:
            rna_clean = re.sub(r"[\s-]", "", code.upper())
            query_str = f"identifiantAssociationUniteLegale:{rna_clean}+AND+etablissementSiege:true+AND+etatAdministratifUniteLegale:A"
        results = self._call_api(query_str)
        return results[0] if results else None
