import re
from typing import Any

from .... import _f
from .. import OrganizationAtlasEuropeProvider

FRANCE_SEARCH_FIELDS = {
    "siren": _f("SIREN", description="SIREN number (9 digits, French organization identifier)"),
    "siret": _f("SIRET", description="SIRET number (14 digits, French establishment identifier)"),
    "rna": _f("RNA", description="RNA number (W + 8 digits, French association identifier)"),
    "ape": _f("Core business", description="APE code (French activity code, NAF)"),
    "ape_noun": _f("Ape noun", description="APE nomenclature (e.g., NAFRev2)"),
    "legalform": _f("Legal form", description="Legal form code or description"),
    "slice_effective": _f(
        "Headcount bracket",
        description="Employee headcount bracket code (INSEE tranche d'effectifs)",
    ),
    "registry_type": _f("Registry type"),
    "registry_authority": _f("Registry authority"),
    "since": _f("Since", "date", "Organization creation date"),
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
    services_fields = {
        "search_organization": FRANCE_SEARCH_FIELDS,
        "search_organization_by_reference": FRANCE_SEARCH_FIELDS,
    }

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

    def get_normalize_slice_effective(self, data: dict[str, Any]) -> str | None:
        value = self._fr_value(data, "slice_effective")
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
