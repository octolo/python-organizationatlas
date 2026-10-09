import re
from typing import Any

from .. import OrganizationAtlasEuropeProvider

def _france_field(description: str, value_type: str = "str") -> dict[str, str]:
    return {"description": description, "value_type": value_type}


FRANCE_FIELDS_DESCRIPTIONS = {
    "siren": _france_field("SIREN number (9 digits, French organization identifier)"),
    "rna": _france_field("RNA number (W + 8 digits, French association identifier)"),
    "siret": _france_field("SIRET number (14 digits, French establishment identifier)"),
    "denomination": _france_field("Organization name or legal name"),
    "since": _france_field("Organization creation date", "date"),
    "legalform": _france_field("Legal form code or description"),
    "ape": _france_field("APE code (French activity code, NAF)"),
    "category": _france_field("Organization category (e.g., PME, ETI, GE)"),
    "slice_effective": _france_field("Employee count range code"),
    "is_headquarter": _france_field("Whether this is the organization headquarters", "bool"),
    "address_line1": _france_field("Street number and name"),
    "address_line2": _france_field("Building, apartment, floor (optional)"),
    "address_line3": _france_field("Additional address info (optional)"),
    "city": _france_field("City name"),
    "postal_code": _france_field("Postal code"),
    "state": _france_field("Department code or name"),
    "region": _france_field("Region code or name"),
    "county": _france_field("County or administrative county"),
    "country": _france_field("Country name"),
    "country_code": _france_field("ISO country code (e.g., FR)"),
    "municipality": _france_field("Municipality or commune"),
    "neighbourhood": _france_field("Neighbourhood, quarter, or district"),
    "latitude": _france_field("Latitude coordinate", "float"),
    "longitude": _france_field("Longitude coordinate", "float"),
}

# (pattern, max_length, uppercase)
_CODE_PATTERNS: dict[str, tuple[str, int, bool]] = {
    "siret": (r"^\d{14}$", 14, False),
    "siren": (r"^\d{9}$", 9, False),
    "rna":   (r"^W|w\d{8}$", 9, True),
}


class OrganizationAtlasFranceProvider(OrganizationAtlasEuropeProvider):
    geo_code = "FR"
    geo_country = "france"
    abstract = True
    france_fields = list(FRANCE_FIELDS_DESCRIPTIONS.keys())

    # ------------------------------------------------------------------ #
    # Code validation & formatting                                         #
    # ------------------------------------------------------------------ #

    def _clean_code(self, code: str, upper: bool = False) -> str:
        if not code:
            return ""
        if upper:
            code = code.upper()
        return re.sub(r"[\s-]", "", code)

    def _matches_pattern(self, code: str, kind: str) -> bool:
        pattern, _, upper = _CODE_PATTERNS[kind]
        return bool(re.match(pattern, self._clean_code(code, upper)))

    def _format_code(self, code: str, kind: str) -> str:
        _, length, upper = _CODE_PATTERNS[kind]
        cleaned = self._clean_code(code, upper)
        return cleaned[:length] if len(cleaned) >= length else cleaned

    def is_siret(self, query: str) -> bool:
        return bool(query) and self._matches_pattern(query, "siret")

    def is_siren(self, query: str) -> bool:
        return bool(query) and self._matches_pattern(query, "siren")

    def is_rna(self, query: str) -> bool:
        return bool(query) and self._matches_pattern(query, "rna")

    def _validate_siret(self, siret: str) -> bool:
        return self._matches_pattern(siret, "siret")

    def _validate_siren(self, siren: str) -> bool:
        return self._matches_pattern(siren, "siren")

    def _validate_rna(self, rna: str) -> bool:
        return self._matches_pattern(rna, "rna")

    def _format_siret(self, siret: str) -> str:
        return self._format_code(siret, "siret")

    def _format_siren(self, siren: str) -> str:
        return self._format_code(siren, "siren")

    def _format_rna(self, rna: str) -> str:
        return self._format_code(rna, "rna")

    def _detect_code_type(self, code: str) -> str | None:
        for kind in ("siret", "siren", "rna"):
            if self._matches_pattern(code, kind):
                return kind
        return None

    # ------------------------------------------------------------------ #
    # Address helpers                                                      #
    # ------------------------------------------------------------------ #

    def _build_address_str(
        self,
        numero: Any,
        type_voie: Any,
        libelle: Any,
        code_postal: Any,
        commune: Any,
        country: str | None = None,
    ) -> str | None:
        line1 = [p for p in [numero, type_voie, libelle] if p]
        parts: list[str] = []
        if line1:
            parts.append(" ".join(str(p) for p in line1))
        if code_postal:
            parts.append(str(code_postal))
        if commune:
            parts.append(str(commune))
        if country:
            parts.append(country)
        return ", ".join(parts) if parts else None

    def _build_address_json(
        self,
        numero: Any,
        type_voie: Any,
        libelle: Any,
        code_postal: Any,
        commune: Any,
    ) -> dict[str, Any] | None:
        line1 = [p for p in [numero, type_voie, libelle] if p]
        address_line1 = " ".join(str(p) for p in line1) if line1 else None
        if not address_line1 and not code_postal and not commune:
            return None
        return {
            "address_line1": address_line1,
            "postal_code": code_postal,
            "city": commune,
            "country": self.geo_country,
            "country_code": self.geo_code,
        }

    # ------------------------------------------------------------------ #
    # ProviderKit hook                                                     #
    # ------------------------------------------------------------------ #

    def get_normalize_source_field(self, data: dict[str, Any]) -> str | None:
        reference = self._fr_value(data, "reference")
        if reference not in (None, ""):
            detected = self._detect_code_type(str(reference))
            if detected:
                return detected
        cache = self._service_results_cache.get("search_organization_by_reference", {})
        kwargs = cache.get("kwargs", {})
        code = kwargs.get("code", "")
        return self._detect_code_type(code)

    def _fr_value(self, data: dict[str, Any], field: str) -> Any:
        paths = getattr(self, "fields_associations", {}).get(field)
        if not paths:
            return None
        value = self._get_nested_value(data, paths)
        if value in (None, ""):
            return None
        return value

    def _format_since(self, value: Any) -> str | None:
        if value in (None, ""):
            return None
        text = str(value).strip()
        match = re.match(r"^(\d{4}-\d{2}-\d{2})", text)
        if match:
            return match.group(1)
        return text or None

    def get_normalize_ape(self, data: dict[str, Any]) -> str | None:
        value = self._fr_value(data, "ape")
        if value is None:
            return None
        return str(value).strip() or None

    def get_normalize_ape_noun(self, data: dict[str, Any]) -> str | None:
        value = self._fr_value(data, "ape_noun")
        if value in (None, ""):
            return None
        return str(value).strip() or None

    def get_normalize_legalform(self, data: dict[str, Any]) -> str | None:
        value = self._fr_value(data, "legalform")
        if value is None:
            return None
        return str(value).strip() or None

    def get_normalize_since(self, data: dict[str, Any]) -> str | None:
        return self._format_since(self._fr_value(data, "since"))

    def get_normalize_registry_type(self, data: dict[str, Any]) -> str | None:
        value = self._fr_value(data, "registry_type")
        if not isinstance(value, str) or not value.strip():
            return None
        return value.strip()

    def get_normalize_registry_authority(self, data: dict[str, Any]) -> str | None:
        value = self._fr_value(data, "registry_authority")
        if value is None:
            return None
        return str(value).strip() or None
