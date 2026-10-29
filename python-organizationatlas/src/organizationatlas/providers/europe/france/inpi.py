from typing import Any, cast

import requests

from . import OrganizationAtlasFranceProvider


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
        if response.status_code == 401:
            self._token = None
            token = self._get_token()
            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            }
            response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        return cast("dict[str, Any] | list[dict[str, Any]]", response.json())

    def _content_root(self, data: dict[str, Any]) -> dict[str, Any] | None:
        content = data.get("content")
        if isinstance(content, dict):
            return content
        return self._get_nested_value(data, "formality.content")

    @staticmethod
    def _principal_from_establishments(establishments: Any) -> dict[str, Any] | None:
        if not isinstance(establishments, list):
            return None
        for establishment in establishments:
            if not isinstance(establishment, dict):
                continue
            description = establishment.get("descriptionEtablissement") or {}
            if description.get("indicateurEtablissementPrincipal"):
                return establishment
        return establishments[0] if establishments and isinstance(establishments[0], dict) else None

    def _principal_from_person(self, person: dict[str, Any]) -> dict[str, Any] | None:
        principal = person.get("etablissementPrincipal")
        if isinstance(principal, dict):
            return principal
        for key in ("autresEtablissements", "etablissements"):
            principal = self._principal_from_establishments(person.get(key))
            if principal:
                return principal
        return None

    def _principal_establishment(self, data: dict[str, Any]) -> dict[str, Any] | None:
        content = self._content_root(data)
        if not content:
            return None
        for person_key in ("personneMorale", "personnePhysique"):
            person = content.get(person_key)
            if not isinstance(person, dict):
                continue
            principal = self._principal_from_person(person)
            if principal:
                return principal
        return None

    def _person_name_from_description(self, description: dict[str, Any] | None) -> str | None:
        if not isinstance(description, dict):
            return None
        prenoms = description.get("prenoms") or []
        if isinstance(prenoms, str):
            prenoms = [prenoms]
        first = " ".join(str(p) for p in prenoms if p)
        last = description.get("nomUsage") or description.get("nom")
        parts = [p for p in [first, last] if p]
        return " ".join(parts) if parts else None

    def _denomination_from_entrepreneur(self, data: dict[str, Any]) -> str | None:
        for prefix in (
            "content.personnePhysique.identite.entrepreneur",
            "formality.content.personnePhysique.identite.entrepreneur",
        ):
            entrepreneur = self._get_nested_value(data, prefix)
            if not isinstance(entrepreneur, dict):
                continue
            name = self._person_name_from_description(entrepreneur.get("descriptionPersonne"))
            if name:
                return name
            conjoint = entrepreneur.get("conjoint")
            if isinstance(conjoint, dict):
                name = self._person_name_from_description(conjoint.get("descriptionPersonne"))
                if name:
                    return name
        return None

    @staticmethod
    def _trade_name(establishment: dict[str, Any] | None) -> str | None:
        if not establishment:
            return None
        description = establishment.get("descriptionEtablissement") or {}
        for key in ("nomCommercial", "enseigne", "nomExploitation"):
            value = description.get(key)
            if value:
                return str(value)
        return None

    def get_normalize_denomination(self, data: dict[str, Any]) -> str | None:
        denomination = self._get_nested_value(data, self.fields_associations["denomination"])
        if denomination:
            return str(denomination)

        establishment = self._principal_establishment(data)
        trade_name = self._trade_name(establishment)
        if trade_name:
            return trade_name

        return self._denomination_from_entrepreneur(data)

    def _usable_address(self, addr: Any) -> dict[str, Any] | None:
        if not isinstance(addr, dict):
            return None
        if any(addr.get(key) for key in ("voie", "numVoie", "codePostal", "commune", "complementLocalisation")):
            return addr
        return None

    def _address_record(self, data: dict[str, Any]) -> dict[str, Any] | None:
        establishment = self._principal_establishment(data)
        if establishment:
            addr = self._usable_address(establishment.get("adresse"))
            if addr:
                return addr
        for prefix in self._address_prefixes:
            addr = self._usable_address(self._get_nested_value(data, prefix))
            if addr:
                return addr
        return None

    def _street_line(self, addr: dict[str, Any]) -> str | None:
        """Build the street line without repeating a number already present in ``voie``.

        INPI sometimes returns ``voie`` as the full line (``295 Boulevard Saint-Denis``)
        while ``numVoie`` and ``typeVoie`` are also set.
        """
        numero = str(addr.get("numVoie") or "").strip()
        type_voie = str(addr.get("typeVoie") or "").strip()
        voie = str(addr.get("voie") or "").strip()
        if self._street_has_number(voie, numero):
            return voie
        parts = [part for part in (numero, type_voie, voie) if part]
        return " ".join(parts) or None

    @staticmethod
    def _street_has_number(voie: str, numero: str) -> bool:
        return bool(voie and numero and (voie == numero or voie.startswith(f"{numero} ")))

    def _country_code(self, code: Any) -> str:
        value = str(code or "").strip().upper()
        if value in {"FRA", "FRANCE", ""}:
            return self.geo_code
        return value[:2]

    def _address_payload(self, addr: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "address_line1": self._street_line(addr),
            "address_line2": str(addr.get("complementLocalisation") or "").strip() or None,
            "postal_code": addr.get("codePostal") or None,
            "city": addr.get("commune") or None,
            "country": addr.get("pays") or self.geo_country,
            "country_code": self._country_code(addr.get("codePays")),
        }
        return {key: value for key, value in payload.items() if value not in (None, "")}

    def get_normalize_address_json(self, data: dict[str, Any]) -> dict[str, Any] | None:
        addr = self._address_record(data)
        if not addr:
            return None
        payload = self._address_payload(addr)
        if not any(payload.get(key) for key in ("address_line1", "postal_code", "city")):
            return None
        return payload

    def get_normalize_address(self, data: dict[str, Any]) -> str | None:
        payload = self.get_normalize_address_json(data)
        if not payload:
            return None
        parts = [
            payload.get("address_line1"),
            payload.get("address_line2"),
            payload.get("postal_code"),
            payload.get("city"),
        ]
        text_parts = [str(part) for part in parts if part]
        return ", ".join(text_parts) if text_parts else None

    def get_normalize_description(self, data: dict[str, Any]) -> str | None:
        activite = (
            self._get_nested_value(data, "content.personneMorale.identite.entreprise.activitePrincipale")
            or self._get_nested_value(data, "content.personnePhysique.identite.entreprise.activitePrincipale")
            or self._get_nested_value(data, "formality.content.personneMorale.identite.entreprise.activitePrincipale")
            or self._get_nested_value(data, "formality.content.personnePhysique.identite.entreprise.activitePrincipale")
        )
        nature = (
            self._get_nested_value(data, "content.personneMorale.identite.entreprise.natureJuridique")
            or self._get_nested_value(data, "content.personnePhysique.identite.entreprise.natureJuridique")
            or self._get_nested_value(data, "formality.content.personneMorale.identite.entreprise.natureJuridique")
            or self._get_nested_value(data, "formality.content.personnePhysique.identite.entreprise.natureJuridique")
        )
        parts = [p for p in [activite, nature] if p]
        return " - ".join(parts) if parts else None

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

    def _companies_api_url(self) -> str:
        return f"{self._get_config_or_env('BASE_URL')}/api/companies"

    def _extract_companies(self, result: dict[str, Any] | list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        if not result:
            return []
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            for key in ("companies", "organizations", "data"):
                items = result.get(key)
                if isinstance(items, list):
                    return items
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
        if not code:
            return None
        siren = self._format_siren(code)
        if not self._validate_siren(siren):
            return None
        result = self._call_api(f"{self._companies_api_url()}/{siren}")
        return result if isinstance(result, dict) else None
