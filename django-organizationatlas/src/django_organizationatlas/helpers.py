"""Helper functions for organization data management."""

import json

from django.db import IntegrityError, transaction
from organizationatlas import ORGANIZATIONATLAS_SEARCH_COMPANY_FIELDS
from organizationatlas.providers import get_search_organization_fields

from .models import (
    OrganizationAtlasAddress,
    OrganizationAtlasData,
    OrganizationAtlasDataType,
    OrganizationAtlasOrganization,
)

_SEARCH_FIELDS = get_search_organization_fields()

# World-level fields are stored on the organization, its addresses or used as keys;
# only country-level fields (plus denomination, for history) become OrganizationAtlasData.
_SKIP_FIELDS = frozenset(ORGANIZATIONATLAS_SEARCH_COMPANY_FIELDS) - {"denomination"}


_BASE_FIELDS = (
    ("denomination", "denomination"),
    ("code", "reference"),
    ("source", "backend"),
    ("country_code", "country_code"),
)

_API_TRACE = "apitrace"


def _text(value) -> str:
    if value is None:
        return ""
    return str(value)


def _data_type(key: str, value_type: str | None = None) -> OrganizationAtlasDataType:
    """Shared data type for this key, created the first time it is used."""
    if value_type is None:
        value_type = _SEARCH_FIELDS.get(key, {}).get("format", "str")
    return OrganizationAtlasDataType.for_key(key, value_type)


def _iter_data_fields(obj) -> dict:
    """Return {data_type: value} for every non-empty, non-system field on obj."""
    result = {}
    for field in getattr(obj, "_meta", None) and obj._meta.get_fields() or []:
        name = getattr(field, "name", None) or getattr(field, "attname", None)
        if not name or name in _SKIP_FIELDS:
            continue
        value = getattr(obj, name, None)
        if value is None or value == "":
            continue
        result[name] = str(value)
    return result


def _incoming_data(obj) -> dict:
    """Data rows carried by a search result, keyed by data_type."""
    payload = {}
    source_field = getattr(obj, "source_field", None)
    reference = getattr(obj, "reference", None)
    if source_field and reference not in (None, ""):
        payload[str(source_field)] = str(reference)
    for data_type, value in _iter_data_fields(obj).items():
        payload.setdefault(data_type, value)
    return payload


def _address_items(value) -> dict:
    if not value:
        return {}
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return {"address_line1": value}
    if not isinstance(value, dict):
        return {"address_line1": str(value)}
    return {key: str(item) for key, item in value.items() if item not in (None, "")}


def _apply_base_fields(organization, obj) -> None:
    changed = False
    for model_field, incoming_field in _BASE_FIELDS:
        incoming = getattr(obj, incoming_field, None)
        if incoming in (None, ""):
            continue
        if _text(getattr(organization, model_field)) == _text(incoming):
            continue
        setattr(organization, model_field, incoming)
        changed = True
    if changed:
        organization.save()


def _upsert_data(organization, obj) -> None:
    source = getattr(obj, "backend", None) or ""
    country = getattr(obj, "country_code", None) or ""
    for data_type, value in _incoming_data(obj).items():
        datatype = _data_type(data_type)
        current = (
            organization.to_organizationatlasdata.filter(
                data_type=datatype,
                valid_to__isnull=True,
            )
            .order_by("-created_at")
            .first()
        )
        if current is None:
            OrganizationAtlasData.objects.create(
                organization=organization,
                source=source,
                country_code=country,
                data_type=datatype,
                value=value,
            )
            continue
        if _text(current.value) == _text(value):
            continue
        current.value = value
        current.source = source
        current.country_code = country
        try:
            with transaction.atomic():
                current.save()
        except IntegrityError:
            current.refresh_from_db()
            current.value = value
            current.save(update_fields=["value"])


def _api_trace_value(obj) -> str | None:
    """JSON of the provider payload that produced this search result."""
    raw = getattr(obj, "data_source", None)
    if raw in (None, ""):
        return None
    if isinstance(raw, str):
        try:
            json.loads(raw)
        except json.JSONDecodeError:
            return json.dumps(raw, ensure_ascii=False)
        return raw
    return json.dumps(raw, ensure_ascii=False, default=str)


def _save_api_trace(organization, obj) -> None:
    value = _api_trace_value(obj)
    if not value:
        return
    source = getattr(obj, "backend", None) or ""
    country = getattr(obj, "country_code", None) or ""
    datatype = _data_type(_API_TRACE, "json")
    current = (
        organization.to_organizationatlasdata.filter(
            data_type=datatype,
            valid_to__isnull=True,
        )
        .order_by("-created_at")
        .first()
    )
    if current is None:
        OrganizationAtlasData.objects.create(
            organization=organization,
            source=source,
            country_code=country,
            data_type=datatype,
            value=value,
        )
        return
    if _text(current.value) == value:
        return
    current.value = value
    current.source = source
    current.country_code = country
    try:
        with transaction.atomic():
            current.save()
    except IntegrityError:
        current.refresh_from_db()
        current.value = value
        current.save(update_fields=["value"])


def _refresh_address(organization, obj) -> None:
    new_address = getattr(obj, "address_json", None)
    if not new_address:
        return
    headquarters = list(organization.to_organizationatlasaddress.filter(is_headquarters=True))
    incoming = _address_items(new_address)
    if any(_address_items(row.address) == incoming for row in headquarters):
        return
    for row in headquarters:
        row.is_headquarters = False
        row.save(update_fields=["is_headquarters"])
    OrganizationAtlasAddress.objects.create(
        organization=organization,
        source=getattr(obj, "backend", None),
        country_code=getattr(obj, "country_code", None) or None,
        address=new_address,
        is_headquarters=True,
    )


def fetch_organization_for_refresh(code: str, provider_name: str):
    """Call the same reference search used when creating an organization."""
    from .models.virtuals.organization import OrganizationAtlasVirtualOrganization

    if not code or not provider_name:
        return None
    return OrganizationAtlasVirtualOrganization.objects.get_queryset_command(
        "search_organization_by_reference",
        code=code,
        attribute_search={"name": provider_name},
        ignore_cache=True,
    ).first()


@transaction.atomic
def create_organization(obj):
    organization = OrganizationAtlasOrganization.objects.create(
        **{model_field: getattr(obj, incoming_field, None) for model_field, incoming_field in _BASE_FIELDS}
    )
    source = obj.backend
    country = obj.country_code or ""
    for data_type, value in _incoming_data(obj).items():
        OrganizationAtlasData.objects.update_or_create(
            organization=organization,
            source=source,
            country_code=country,
            data_type=_data_type(data_type),
            defaults={"value": value},
        )

    if obj.address_json:
        OrganizationAtlasAddress.objects.create(
            organization=organization,
            source=obj.backend,
            country_code=obj.country_code,
            address=obj.address_json,
            is_headquarters=True,
        )
    _save_api_trace(organization, obj)

    return organization


@transaction.atomic
def refresh_organization(organization, obj):
    """Update an organization from a search result.

    Data rows are matched on data_type: a different value replaces the current
    one, a missing key is inserted. A changed address is kept and loses the
    headquarters flag; the new address becomes headquarters. Base fields are
    written only when the incoming value differs.
    """
    _apply_base_fields(organization, obj)
    _upsert_data(organization, obj)
    _refresh_address(organization, obj)
    _save_api_trace(organization, obj)
    return organization
