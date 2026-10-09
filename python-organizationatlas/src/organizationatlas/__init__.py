"""OrganizationAtlas — field schemas and version."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("python-organizationatlas")
except PackageNotFoundError:
    __version__ = "0.0.0.dev"


def _f(label: str, fmt: str = "str") -> dict:
    return {"label": label, "description": label, "format": fmt}


_ID_FIELD = _f("Organizationatlas ID")


def _list_response_fields(name: str, label: str) -> dict:
    return {name: _f(label, "list"), "organizationatlas_id": _ID_FIELD}


ORGANIZATIONATLAS_SEARCH_COMPANY_FIELDS = {
    "denomination": _f("Denomination"),
    "reference": _f("Reference"),
    "source_field": _f("Source field"),
    "siren": _f("SIREN"),
    "siret": _f("SIRET"),
    "rna": _f("RNA"),
    "country_code": _f("Country code"),
    "address": _f("Address"),
    "address_json": _f("Address JSON", "json"),
    "ape": _f("Core business"),
    "ape_noun": _f("Ape noun"),
    "legalform": _f("Legal form"),
    "registry_type": _f("Registry type"),
    "registry_authority": _f("Registry authority"),
    "since": _f("Since"),
    "organizationatlas_id": _ID_FIELD,
    "data_source": _f("Data source"),
    "backend": _f("Backend display name"),
    "backend_name": _f("Simple backend name (e.g., insee)"),
}

ORGANIZATIONATLAS_GET_COMPANY_DOCUMENTS_FIELDS = _list_response_fields("documents", "Documents")
ORGANIZATIONATLAS_GET_COMPANY_EVENTS_FIELDS = _list_response_fields("events", "Events")
ORGANIZATIONATLAS_GET_COMPANY_OFFICERS_FIELDS = _list_response_fields("officers", "Officers")
ORGANIZATIONATLAS_GET_ULTIMATE_BENEFICIAL_OWNERS_FIELDS = _list_response_fields(
    "ultimate_beneficial_owners", "Ultimate beneficial owners"
)

ORGANIZATIONATLAS_GET_REFERENTIEL_FIELDS = {
    "category": _f("Category"),
    "code": _f("Code"),
    "description": _f("Description"),
    "characteristics": _f("Characteristics"),
    "priority": _f("Priority", "int"),
    "usage_type": _f("Usage Type"),
}

__all__ = [
    "ORGANIZATIONATLAS_SEARCH_COMPANY_FIELDS",
    "ORGANIZATIONATLAS_GET_COMPANY_DOCUMENTS_FIELDS",
    "ORGANIZATIONATLAS_GET_COMPANY_EVENTS_FIELDS",
    "ORGANIZATIONATLAS_GET_COMPANY_OFFICERS_FIELDS",
    "ORGANIZATIONATLAS_GET_ULTIMATE_BENEFICIAL_OWNERS_FIELDS",
    "ORGANIZATIONATLAS_GET_REFERENTIEL_FIELDS",
]
