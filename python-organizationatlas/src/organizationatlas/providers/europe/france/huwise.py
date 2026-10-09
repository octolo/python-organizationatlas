from typing import Any, cast

import requests

from . import OrganizationAtlasFranceProvider


class HuwiseProvider(OrganizationAtlasFranceProvider):
    name = "huwise"
    display_name = "Huwise"
    description = "Open data platform aggregating French public datasets"
    required_packages = ["requests"]
    config_keys = ["SIREN_DATASET_ID", "BASE_URL"]
    config_defaults = {
        "SIREN_DATASET_ID": "economicref-france-sirene-v3",
        "BASE_URL": "https://hub.huwise.com",
    }
    documentation_url = "https://docs.huwise.com"
    site_url = "https://huwise.com"
    status_url = None
    priority = 3

    fields_associations = {
        "denomination": ("denominationunitelegale", "denominationusuelleetablissement"),
        "reference": ("identifiantassociationunitelegale", "siret", "siren"),
        "siren": "siren",
        "siret": "siret",
        "rna": "identifiantassociationunitelegale",
        "ape": "activiteprincipaleunitelegale",
        "ape_noun": "nomenclatureactiviteprincipaleunitelegale",
        "legalform": "categoriejuridiqueunitelegale",
        "since": "datecreationunitelegale",
        "address": (
            "numerovoieetablissement",
            "typevoieetablissement",
            "libellevoieetablissement",
            "codepostaletablissement",
            "libellecommuneetablissement",
        ),
    }

    def _get_address_parts(self, data: dict[str, Any]) -> tuple:
        return (
            self._get_nested_value(data, "numerovoieetablissement"),
            self._get_nested_value(data, "typevoieetablissement"),
            self._get_nested_value(data, "libellevoieetablissement"),
            self._get_nested_value(data, "codepostaletablissement"),
            self._get_nested_value(data, "libellecommuneetablissement"),
        )

    def get_normalize_address_json(self, data: dict[str, Any]) -> dict[str, Any] | None:
        return self._build_address_json(*self._get_address_parts(data))

    def get_normalize_address(self, data: dict[str, Any]) -> str | None:
        return self._build_address_str(*self._get_address_parts(data))

    def _call_api(self, query: str) -> dict[str, Any]:
        dataset_id = self._get_config_or_env("SIREN_DATASET_ID", default="economicref-france-sirene-v3")
        base_url = self._get_config_or_env("BASE_URL", default="https://hub.huwise.com")
        url = f"{base_url}/api/explore/v2.1/catalog/datasets/{dataset_id}/records/"
        params = {"where": f"search({query})", "limit": 20, "lang": "fr", "offset": 0, "timezone": "Europe/Paris"}
        response = requests.get(url, params=params, headers={}, timeout=10)
        response.raise_for_status()
        return cast("dict[str, Any]", response.json())

    def search_organization(self, query: str, raw: bool = False, **kwargs: Any) -> list[dict[str, Any]]:
        if not query:
            return []
        data = self._call_api(f'"{query}"')
        return cast("list[dict[str, Any]]", data.get("results", []))

    def search_organization_by_reference(self, code: str, raw: bool = False, **kwargs: Any) -> dict[str, Any] | None:
        if not code:
            return None
        siren = self._format_siren(code)
        if not self._validate_siren(siren):
            return None
        data = self._call_api(f'"{siren}"')
        results = data.get("results", [])
        return results[0] if results else None
