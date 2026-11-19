from typing import Any

_ENTREPRENEUR_PREFIXES = (
    "content.personnePhysique.identite.entrepreneur",
    "formality.content.personnePhysique.identite.entrepreneur",
)
_ACTIVITY_PATHS = (
    "content.personneMorale.identite.entreprise.activitePrincipale",
    "content.personnePhysique.identite.entreprise.activitePrincipale",
    "formality.content.personneMorale.identite.entreprise.activitePrincipale",
    "formality.content.personnePhysique.identite.entreprise.activitePrincipale",
)
_LEGAL_NATURE_PATHS = (
    "content.personneMorale.identite.entreprise.natureJuridique",
    "content.personnePhysique.identite.entreprise.natureJuridique",
    "formality.content.personneMorale.identite.entreprise.natureJuridique",
    "formality.content.personnePhysique.identite.entreprise.natureJuridique",
)
_ADDRESS_KEYS = ("voie", "numVoie", "codePostal", "commune", "complementLocalisation")
_ADDRESS_LINE_KEYS = ("address_line1", "postal_code", "city")


def principal_from_establishments(establishments: Any) -> dict[str, Any] | None:
    if not isinstance(establishments, list):
        return None
    for establishment in establishments:
        if not isinstance(establishment, dict):
            continue
        description = establishment.get("descriptionEtablissement") or {}
        if description.get("indicateurEtablissementPrincipal"):
            return establishment
    if establishments and isinstance(establishments[0], dict):
        return establishments[0]
    return None


def principal_from_person(person: dict[str, Any]) -> dict[str, Any] | None:
    principal = person.get("etablissementPrincipal")
    if isinstance(principal, dict):
        return principal
    for key in ("autresEtablissements", "etablissements"):
        principal = principal_from_establishments(person.get(key))
        if principal:
            return principal
    return None


def person_name_from_description(description: dict[str, Any] | None) -> str | None:
    if not isinstance(description, dict):
        return None
    prenoms = description.get("prenoms") or []
    if isinstance(prenoms, str):
        prenoms = [prenoms]
    first = " ".join(str(part) for part in prenoms if part)
    last = description.get("nomUsage") or description.get("nom")
    parts = [part for part in (first, last) if part]
    return " ".join(parts) if parts else None


def _name_from_entrepreneur(entrepreneur: dict[str, Any]) -> str | None:
    name = person_name_from_description(entrepreneur.get("descriptionPersonne"))
    if name:
        return name
    conjoint = entrepreneur.get("conjoint")
    if isinstance(conjoint, dict):
        return person_name_from_description(conjoint.get("descriptionPersonne"))
    return None


def denomination_from_entrepreneur(data: dict[str, Any], get_nested) -> str | None:
    for prefix in _ENTREPRENEUR_PREFIXES:
        entrepreneur = get_nested(data, prefix)
        if not isinstance(entrepreneur, dict):
            continue
        name = _name_from_entrepreneur(entrepreneur)
        if name:
            return name
    return None


def trade_name(establishment: dict[str, Any] | None) -> str | None:
    if not establishment:
        return None
    description = establishment.get("descriptionEtablissement") or {}
    for key in ("nomCommercial", "enseigne", "nomExploitation"):
        value = description.get(key)
        if value:
            return str(value)
    return None


def usable_address(addr: Any) -> dict[str, Any] | None:
    if not isinstance(addr, dict):
        return None
    if any(addr.get(key) for key in _ADDRESS_KEYS):
        return addr
    return None


def _street_has_number(voie: str, numero: str) -> bool:
    return bool(voie and numero and (voie == numero or voie.startswith(f"{numero} ")))


def street_line(addr: dict[str, Any]) -> str | None:
    """Build the street line without repeating a number already present in ``voie``.

    INPI sometimes returns ``voie`` as the full line (``295 Boulevard Saint-Denis``)
    while ``numVoie`` and ``typeVoie`` are also set.
    """
    numero = str(addr.get("numVoie") or "").strip()
    type_voie = str(addr.get("typeVoie") or "").strip()
    voie = str(addr.get("voie") or "").strip()
    if _street_has_number(voie, numero):
        return voie
    parts = [part for part in (numero, type_voie, voie) if part]
    return " ".join(parts) or None


def country_code(code: Any, geo_code: str) -> str:
    value = str(code or "").strip().upper()
    if value in {"FRA", "FRANCE", ""}:
        return geo_code
    return value[:2]


def address_payload(addr: dict[str, Any], geo_code: str, geo_country: str) -> dict[str, Any]:
    payload = {
        "address_line1": street_line(addr),
        "address_line2": str(addr.get("complementLocalisation") or "").strip() or None,
        "postal_code": addr.get("codePostal") or None,
        "city": addr.get("commune") or None,
        "country": addr.get("pays") or geo_country,
        "country_code": country_code(addr.get("codePays"), geo_code),
    }
    return {key: value for key, value in payload.items() if value not in (None, "")}


def filled_address(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not payload:
        return None
    if not any(payload.get(key) for key in _ADDRESS_LINE_KEYS):
        return None
    return payload


def address_text(payload: dict[str, Any] | None) -> str | None:
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


def _first_nested(data: dict[str, Any], get_nested, paths: tuple[str, ...]) -> Any:
    for path in paths:
        value = get_nested(data, path)
        if value:
            return value
    return None


def description_text(data: dict[str, Any], get_nested) -> str | None:
    activite = _first_nested(data, get_nested, _ACTIVITY_PATHS)
    nature = _first_nested(data, get_nested, _LEGAL_NATURE_PATHS)
    parts = [part for part in (activite, nature) if part]
    return " - ".join(parts) if parts else None
