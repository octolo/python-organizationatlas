import re
from typing import Any, cast
from urllib.parse import quote, urlencode

import requests

from . import OrganizationAtlasFranceProvider


_SIRENE_API = "https://api.insee.fr/api-sirene/3.11"

# Sirene period variables that carry a successive value. Change flags are omitted.
_LEGAL_UNIT_HISTORY_FIELDS = {
    "denominationUniteLegale": "denomination",
    "denominationUsuelle1UniteLegale": "usual_denomination_1",
    "denominationUsuelle2UniteLegale": "usual_denomination_2",
    "denominationUsuelle3UniteLegale": "usual_denomination_3",
    "nomUniteLegale": "birth_name",
    "nomUsageUniteLegale": "usage_name",
    "etatAdministratifUniteLegale": "administrative_status",
    "categorieJuridiqueUniteLegale": "legalform",
    "activitePrincipaleUniteLegale": "ape",
    "nomenclatureActivitePrincipaleUniteLegale": "ape_noun",
    "nicSiegeUniteLegale": "headquarters_nic",
    "economieSocialeSolidaireUniteLegale": "social_economy",
    "societeMissionUniteLegale": "mission_company",
    "caractereEmployeurUniteLegale": "employer",
}

_ESTABLISHMENT_HISTORY_FIELDS = {
    "etatAdministratifEtablissement": "establishment_status",
    "enseigne1Etablissement": "trade_sign_1",
    "enseigne2Etablissement": "trade_sign_2",
    "enseigne3Etablissement": "trade_sign_3",
    "denominationUsuelleEtablissement": "establishment_usual_denomination",
    "activitePrincipaleEtablissement": "establishment_ape",
    "nomenclatureActivitePrincipaleEtablissement": "establishment_ape_noun",
    "caractereEmployeurEtablissement": "establishment_employer",
}


def _escape_search_phrase(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _clean_history_value(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text == "[ND]":
        return None
    return text


def _period_bound(period: dict[str, Any], key: str) -> str | None:
    value = period.get(key)
    if value in (None, ""):
        return None
    return str(value)[:10]


def _history_from_periods(
    periods: list[dict[str, Any]],
    field_map: dict[str, str],
    *,
    siren: str,
    siret: str | None,
    scope: str,
) -> list[dict[str, Any]]:
    """One row per distinct value.

    A Sirene period opens whenever any historized variable changes. Consecutive
    periods that keep the same value for one field stay a single validity range.
    """
    ordered = sorted(periods, key=lambda period: _period_bound(period, "dateDebut") or "")
    open_runs: dict[str, dict[str, Any]] = {}
    records: list[dict[str, Any]] = []

    for period in ordered:
        start = _period_bound(period, "dateDebut")
        end = _period_bound(period, "dateFin")
        for source_key, field in field_map.items():
            value = _clean_history_value(period.get(source_key))
            current = open_runs.get(field)
            if current and current["value"] == value:
                current["valid_to"] = end
                continue
            if current:
                records.append(open_runs.pop(field))
            if value is None:
                continue
            open_runs[field] = {
                "field": field,
                "value": value,
                "valid_from": start,
                "valid_to": end,
                "scope": scope,
                "siren": siren,
                "siret": siret,
                "reference": siren,
            }

    records.extend(open_runs.values())
    return records


def _current_headquarters_siret(unite_legale: dict[str, Any]) -> str | None:
    siren = unite_legale.get("siren")
    periods = unite_legale.get("periodesUniteLegale") or []
    if not siren or not periods:
        return None
    current = next((period for period in periods if not period.get("dateFin")), None)
    source = current or max(periods, key=lambda period: period.get("dateDebut") or "")
    nic = _clean_history_value(source.get("nicSiegeUniteLegale"))
    if not nic:
        return None
    return f"{siren}{nic}"


def _legal_unit_history(unite_legale: dict[str, Any], siren: str) -> list[dict[str, Any]]:
    return _history_from_periods(
        unite_legale.get("periodesUniteLegale") or [],
        _LEGAL_UNIT_HISTORY_FIELDS,
        siren=str(unite_legale.get("siren") or siren),
        siret=None,
        scope="legal_unit",
    )


def _establishment_history(
    establishment: dict[str, Any],
    *,
    siren: str,
    siret: str,
) -> list[dict[str, Any]]:
    return _history_from_periods(
        establishment.get("periodesEtablissement") or [],
        _ESTABLISHMENT_HISTORY_FIELDS,
        siren=siren,
        siret=siret,
        scope="establishment",
    )


def _payload_object(payload: dict[str, Any] | None, key: str) -> dict[str, Any]:
    if not payload:
        return {}
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def _history_sort_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return row["scope"], row["field"], row["valid_from"] or ""


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
        "category": "uniteLegale.categorieEntreprise",
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
            quote_via=lambda value, _safe="", encoding=None, errors=None: quote(
                value,
                safe="+",
                encoding=encoding,
                errors=errors,
            ),
        )
        url = f"{_SIRENE_API}/{endpoint}?{query_string}"
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
            result = self.search_organization_by_reference(query)
            return [result] if result else []
        query_clean = query.replace("+", " ").strip()
        return self._call_api(
            f'denominationUniteLegale:"{_escape_search_phrase(query_clean)}"',
            endpoint="siret",
        )

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

    def _fetch_sirene(self, path: str) -> dict[str, Any] | None:
        api_key = self._get_config_or_env("API_KEY")
        if not api_key:
            raise ValueError("INSEE API_KEY is required but not configured")
        response = requests.get(
            f"{_SIRENE_API}/{path}",
            headers={"Accept": "application/json", "X-INSEE-Api-Key-Integration": api_key},
            timeout=10,
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else None

    def _identifiers_for_history(self, code: str) -> tuple[str | None, str | None]:
        code_type = self._detect_code_type(code)
        if code_type == "siren":
            return self._format_siren(code), None
        if code_type == "siret":
            siret = self._format_siret(code)
            return siret[:9], siret
        if code_type == "rna":
            rna = self._format_rna(code)
            results = self._call_api(
                f"identifiantAssociationUniteLegale:{rna}"
                "+AND+etablissementSiege:true"
                "+AND+etatAdministratifUniteLegale:A"
            )
            if not results:
                return None, None
            item = results[0]
            siren = item.get("siren")
            result_siret = item.get("siret")
            if not siren:
                return None, None
            return str(siren), str(result_siret) if result_siret else None
        return None, None

    def get_organization_history(self, code: str, raw: bool = False, **kwargs: Any) -> list[dict[str, Any]]:
        if not code:
            return []
        siren, siret = self._identifiers_for_history(code)
        if not siren:
            return []
        payload = self._fetch_sirene(f"siren/{siren}")
        unite_legale = _payload_object(payload, "uniteLegale")
        if not unite_legale:
            return []
        establishment_siret = siret or _current_headquarters_siret(unite_legale)
        history_siren = str(unite_legale.get("siren") or siren)
        records = _legal_unit_history(unite_legale, history_siren)
        if establishment_siret:
            establishment_payload = self._fetch_sirene(f"siret/{establishment_siret}")
            establishment = _payload_object(establishment_payload, "etablissement")
            records.extend(
                _establishment_history(
                    establishment,
                    siren=history_siren,
                    siret=establishment_siret,
                )
            )
        records.sort(key=_history_sort_key)
        return records
