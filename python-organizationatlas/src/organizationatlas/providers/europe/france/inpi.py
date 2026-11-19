import logging
from http import HTTPStatus
from typing import Any, cast

import requests

from . import OrganizationAtlasFranceProvider
from .inpi_records import (
    address_payload,
    address_text,
    denomination_from_entrepreneur,
    description_text,
    filled_address,
    principal_from_person,
    trade_name,
    usable_address,
)

logger = logging.getLogger(__name__)


class InpiProvider(OrganizationAtlasFranceProvider):
    name = "inpi"
    display_name = "INPI"
    description = "Institut National de la Propriété Industrielle - Registre national des entreprises"
    required_packages = ["requests"]
    config_keys = ["API_USERNAME", "API_PASSWORD", "BASE_URL", "SSO_URL"]
    config_defaults = {
        "BASE_URL": "https://registre-national-entreprises.inpi.fr",
        "SSO_URL": "https://registre-national-entreprises.inpi.fr/api/sso/login",
    }
    documentation_url = "https://www.inpi.fr/fr/services-et-outils/api"
    site_url = "https://www.inpi.fr"
    status_url = None
    priority = 5

    _address_prefixes = (
        "content.personneMorale.adresseEntreprise.adresse",
        "content.personneMorale.etablissementPrincipal.adresse",
        "content.personnePhysique.etablissementPrincipal.adresse",
        "content.personnePhysique.adresseEntreprise.adresse",
        # Legacy RNE wrapper (pre-2023 payloads)
        "formality.content.personneMorale.adresseEntreprise.adresse",
        "formality.content.personneMorale.etablissementPrincipal.adresse",
        "formality.content.personnePhysique.etablissementPrincipal.adresse",
        "formality.content.personnePhysique.adresseEntreprise.adresse",
    )

    fields_associations = {
        "reference": (
            "content.personneMorale.etablissementPrincipal.descriptionEtablissement.siret",
            "siren",
            "formality.siren",
            "content.personneMorale.identite.entreprise.siren",
            "formality.content.personneMorale.etablissementPrincipal.descriptionEtablissement.siret",
            "formality.content.personneMorale.identite.entreprise.siren",
        ),
        "siren": (
            "siren",
            "formality.siren",
            "content.personneMorale.identite.entreprise.siren",
            "formality.content.personneMorale.identite.entreprise.siren",
        ),
        "siret": (
            "content.personneMorale.etablissementPrincipal.descriptionEtablissement.siret",
            "formality.content.personneMorale.etablissementPrincipal.descriptionEtablissement.siret",
            "content.personnePhysique.etablissementPrincipal.descriptionEtablissement.siret",
            "formality.content.personnePhysique.etablissementPrincipal.descriptionEtablissement.siret",
        ),
        "ape": (
            "content.personneMorale.identite.entreprise.codeApe",
            "content.personneMorale.etablissementPrincipal.descriptionEtablissement.codeApe",
            "content.personnePhysique.etablissementPrincipal.descriptionEtablissement.codeApe",
            "formality.content.personneMorale.identite.entreprise.codeApe",
            "formality.content.personneMorale.etablissementPrincipal.descriptionEtablissement.codeApe",
            "formality.content.personnePhysique.etablissementPrincipal.descriptionEtablissement.codeApe",
        ),
        "legalform": (
            "content.personneMorale.identite.entreprise.formeJuridique",
            "content.natureCreation.formeJuridique",
            "formality.content.personneMorale.identite.entreprise.formeJuridique",
            "formality.content.natureCreation.formeJuridique",
            "formality.formeJuridique",
            "formeJuridique",
        ),
        "since": (
            "content.natureCreation.dateCreation",
            "formality.content.natureCreation.dateCreation",
            "content.registreAnterieur.rncs.dateImmatriculation",
            "formality.content.registreAnterieur.rncs.dateImmatriculation",
        ),
        "registry_type": (
            "content.registreAnterieur.rncs.estPresent",
            "formality.content.registreAnterieur.rncs.estPresent",
        ),
        "registry_authority": (
            "content.personneMorale.observations.rcs.rcs.nomGreffe",
            "formality.content.personneMorale.observations.rcs.rcs.nomGreffe",
            "content.personnePhysique.observations.rcs.rcs.nomGreffe",
            "formality.content.personnePhysique.observations.rcs.rcs.nomGreffe",
            "greffe.nom",
            "nomGreffe",
        ),
        "denomination": (
            "content.personneMorale.identite.entreprise.denomination",
            "content.personnePhysique.identite.entreprise.denomination",
            "content.personneMorale.identite.description.sigle",
            "content.personnePhysique.etablissementPrincipal.descriptionEtablissement.nomCommercial",
            "content.personneMorale.etablissementPrincipal.descriptionEtablissement.nomCommercial",
            "companyName",
            "formality.content.personneMorale.identite.entreprise.denomination",
            "formality.content.personnePhysique.identite.entreprise.denomination",
        ),
    }

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self._token: str | None = None

    def _get_token(self) -> str:
        if self._token:
            return self._token
        username = self._get_config_or_env("API_USERNAME")
        password = self._get_config_or_env("API_PASSWORD")
        if not username or not password:
            raise ValueError("INPI API_USERNAME and API_PASSWORD are required")
        response = requests.post(
            self._get_config_or_env("SSO_URL"),
            json={"username": username, "password": password},
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        self._warn_if_rate_limited(response)
        response.raise_for_status()
        data = response.json()
        token = data.get("token") or data.get("access_token")
        if not token:
            raise ValueError("INPI authentication response does not contain a token")
        self._token = str(token)
        return self._token

    def _call_api(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any] | list[dict[str, Any]] | None:
        token = self._get_token()
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        response = requests.get(url, headers=headers, params=params, timeout=10)
        if response.status_code == HTTPStatus.UNAUTHORIZED:
            self._token = None
            token = self._get_token()
            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            }
            response = requests.get(url, headers=headers, params=params, timeout=10)
        if response.status_code == HTTPStatus.NOT_FOUND:
            return None
        self._warn_if_rate_limited(response)
        response.raise_for_status()
        return cast("dict[str, Any] | list[dict[str, Any]]", response.json())

    def _content_root(self, data: dict[str, Any]) -> dict[str, Any] | None:
        content = data.get("content")
        if isinstance(content, dict):
            return content
        return self._get_nested_value(data, "formality.content")

    def _principal_establishment(self, data: dict[str, Any]) -> dict[str, Any] | None:
        content = self._content_root(data)
        if not content:
            return None
        for person_key in ("personneMorale", "personnePhysique"):
            person = content.get(person_key)
            if not isinstance(person, dict):
                continue
            principal = principal_from_person(person)
            if principal:
                return principal
        return None

    def get_normalize_denomination(self, data: dict[str, Any]) -> str | None:
        denomination = self._get_nested_value(data, self.fields_associations["denomination"])
        if denomination:
            return str(denomination)

        establishment = self._principal_establishment(data)
        commercial_name = trade_name(establishment)
        if commercial_name:
            return commercial_name

        return denomination_from_entrepreneur(data, self._get_nested_value)

    def _address_record(self, data: dict[str, Any]) -> dict[str, Any] | None:
        establishment = self._principal_establishment(data)
        if establishment:
            addr = usable_address(establishment.get("adresse"))
            if addr:
                return addr
        for prefix in self._address_prefixes:
            addr = usable_address(self._get_nested_value(data, prefix))
            if addr:
                return addr
        return None

    def get_normalize_address_json(self, data: dict[str, Any]) -> dict[str, Any] | None:
        addr = self._address_record(data)
        if not addr:
            return None
        return filled_address(address_payload(addr, self.geo_code, self.geo_country))

    def get_normalize_address(self, data: dict[str, Any]) -> str | None:
        return address_text(self.get_normalize_address_json(data))

    def get_normalize_description(self, data: dict[str, Any]) -> str | None:
        return description_text(data, self._get_nested_value)

    def get_normalize_registry_type(self, data: dict[str, Any]) -> str | None:
        present = self._get_nested_value(
            data,
            self.fields_associations["registry_type"],
        )
        if present is True or (
            isinstance(present, str) and present.strip().lower() == "true"
        ):
            return "RNCS"
        return None

    @staticmethod
    def _warn_if_rate_limited(response: requests.Response) -> None:
        if response.status_code != HTTPStatus.TOO_MANY_REQUESTS:
            return
        logger.warning(
            "INPI rate limit reached (HTTP 429). This address is temporarily blocked."
        )

    def _companies_api_url(self) -> str:
        return f"{self._get_config_or_env('BASE_URL')}/api/companies"

    def _siren_from_code(self, code: str) -> str | None:
        if self.is_siren(code):
            return self._format_siren(code)
        if self.is_siret(code):
            return self._format_siret(code)[:9]
        return None

    def _extract_companies(self, result: dict[str, Any] | list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        if not result:
            return []
        if isinstance(result, list):
            return [item for item in result if isinstance(item, dict)]
        if isinstance(result, dict):
            for key in ("companies", "organizations", "data"):
                items = result.get(key)
                if isinstance(items, list):
                    return [item for item in items if isinstance(item, dict)]
            if any(result.get(key) for key in ("siren", "formality", "content", "companyName")):
                return [result]
        return []

    def search_organization(self, query: str, raw: bool = False, **kwargs: Any) -> list[dict[str, Any]]:
        if not query:
            return []
        if self.is_siren(query) or self.is_siret(query):
            detail = self.search_organization_by_reference(query, raw=raw, **kwargs)
            return [detail] if detail else []
        result = self._call_api(
            self._companies_api_url(),
            params={"companyName": query, "page": 1, "pageSize": 20},
        )
        return self._extract_companies(result)

    def search_organization_by_reference(self, code: str, raw: bool = False, **kwargs: Any) -> dict[str, Any] | None:
        siren = self._siren_from_code(code)
        if not siren:
            return None
        companies = self._extract_companies(
            self._call_api(
                self._companies_api_url(),
                params={"page": 1, "pageSize": 1, "siren[]": siren},
            )
        )
        if companies:
            return companies[0]
        companies = self._extract_companies(self._call_api(f"{self._companies_api_url()}/{siren}"))
        return companies[0] if companies else None
