import re
from typing import Any, cast
from urllib.parse import quote

import requests

from . import OrganizationAtlasFranceProvider


class EntdatagouvProvider(OrganizationAtlasFranceProvider):
    name = "entdatagouv"
    display_name = "data.gouv.fr"
    description = "French open data platform for public entities and datasets"
    required_packages = ["requests"]
    config_keys = ["BASE_URL"]
    config_defaults = {
        "BASE_URL": "https://recherche-entreprises.api.gouv.fr",
    }
    documentation_url = "https://www.data.gouv.fr/api"
    site_url = "https://www.data.gouv.fr"
    status_url = None
    priority = 2

    fields_associations = {
        "denomination": ["nom_raison_sociale", "nom_complet"],
        "reference": ["complements.identifiant_association", "siren", "siege.siren", "siege.siret"],
        "siren": "siren",
        "siret": "siege.siret",
        "rna": ["complements.identifiant_association", "id_association"],
        "ape": ["siege.activite_principale", "activite_principale"],
        "legalform": "nature_juridique",
        "since": ["date_creation", "date_creation_entreprise"],
        "address": (
            "siege.numero_voie",
            "siege.type_voie",
            "siege.libelle_voie",
            "siege.code_postal",
            "siege.libelle_commune",
            "matching_etablissements.0.numero_voie",
            "matching_etablissements.0.type_voie",
            "matching_etablissements.0.libelle_voie",
            "matching_etablissements.0.code_postal",
            "matching_etablissements.0.libelle_commune",
        ),
    }

    _SIEGE_KEYS = ["siege.numero_voie", "matching_etablissements.0.numero_voie"]
    _TYPE_KEYS = ["siege.type_voie", "matching_etablissements.0.type_voie"]
    _LIBELLE_KEYS = ["siege.libelle_voie", "matching_etablissements.0.libelle_voie"]
    _CP_KEYS = ["siege.code_postal", "matching_etablissements.0.code_postal"]
    _COMMUNE_KEYS = ["siege.libelle_commune", "matching_etablissements.0.libelle_commune"]

    def _get_address_parts(self, data: dict[str, Any]) -> tuple:
        return (
            self._get_nested_value(data, self._SIEGE_KEYS),
            self._get_nested_value(data, self._TYPE_KEYS),
            self._get_nested_value(data, self._LIBELLE_KEYS),
            self._get_nested_value(data, self._CP_KEYS),
            self._get_nested_value(data, self._COMMUNE_KEYS),
        )

    def get_normalize_address_line1(self, data: dict[str, Any]) -> str | None:
        nv, tv, lv, _, _ = self._get_address_parts(data)
        parts = [p for p in [nv, tv, lv] if p]
        return " ".join(str(p) for p in parts) if parts else None

    def get_normalize_address_json(self, data: dict[str, Any]) -> dict[str, Any] | None:
        return self._build_address_json(*self._get_address_parts(data))

    def get_normalize_address(self, data: dict[str, Any]) -> str | None:
        return self._build_address_str(*self._get_address_parts(data))

    def _call_api(self, url: str) -> dict[str, Any]:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return cast("dict[str, Any]", response.json())

    def search_organization(self, query: str, raw: bool = False, **kwargs: Any) -> list[dict[str, Any]]:
        if not query:
            return []
        url = f"{self._get_config_or_env('BASE_URL')}/search?q={quote(query)}"
        data = self._call_api(url)
        return cast("list[dict[str, Any]]", data.get("results", []))

    def _get_url_by_reference(self, code: str) -> str | None:
        code_type = self._detect_code_type(code)
        if not code_type:
            return None
        code_clean = re.sub(r"[\s-]", "", code)
        if code_type in ("siren", "siret"):
            return f"{self._get_config_or_env('BASE_URL')}/search?q={code_clean}"
        if code_type == "rna":
            return f"{self._get_config_or_env('BASE_URL')}/api/rna/v1/id/{code_clean}"
        return None

    def search_organization_by_reference(self, code: str, raw: bool = False, **kwargs: Any) -> dict[str, Any] | None:
        if not code:
            return None
        url = self._get_url_by_reference(code)
        if url is None:
            return None
        data = self._call_api(url)
        results = data.get("results", [])
        return results[0] if results else None
