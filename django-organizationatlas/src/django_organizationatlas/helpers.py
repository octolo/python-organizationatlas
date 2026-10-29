"""Helper functions for organization data management."""

import json
from datetime import date, datetime, timedelta

from django.db import IntegrityError, transaction
from organizationatlas import ORGANIZATIONATLAS_SEARCH_COMPANY_FIELDS
from organizationatlas.helpers import get_organization_history
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


class OrganizationHistoryError(ValueError):
    pass


_BASE_FIELDS = (
    ("denomination", "denomination"),
    ("code", "reference"),
    ("source", "backend"),
    ("country_code", "country_code"),
)

_API_TRACE = "apitrace"
_API_HISTORY_TRACE = "apihistorytrace"
_TIMELINE_EXCLUDED_DATA_TYPES = (_API_TRACE, _API_HISTORY_TRACE)


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


def _create_open_data(**fields):
    try:
        with transaction.atomic():
            return OrganizationAtlasData.objects.create(**fields), True
    except IntegrityError as exc:
        try:
            current = OrganizationAtlasData.objects.select_for_update().get(
                organization=fields["organization"],
                source=fields["source"],
                country_code=fields["country_code"],
                data_type=fields["data_type"],
                valid_to__isnull=True,
            )
        except OrganizationAtlasData.DoesNotExist:
            raise exc
        return current, False


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
            organization.to_organizationatlasdata.select_for_update().filter(
                source=source,
                country_code=country,
                data_type=datatype,
                valid_to__isnull=True,
            )
            .order_by("-created_at")
            .first()
        )
        if current is None:
            current, created = _create_open_data(
                organization=organization,
                source=source,
                country_code=country,
                data_type=datatype,
                value=value,
            )
            if created:
                continue
        if _text(current.value) == _text(value):
            continue
        today = date.today()
        if current.valid_from is not None and current.valid_from >= today:
            current.value = value
            current.save(update_fields=["value", "updated_at"])
            continue
        current.valid_to = today - timedelta(days=1)
        current.save(update_fields=["valid_to", "updated_at"])
        OrganizationAtlasData.objects.create(
            organization=organization,
            source=source,
            country_code=country,
            data_type=datatype,
            value=value,
            valid_from=today,
        )


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


def _save_open_json_data(organization, *, key: str, value: str, source: str, country: str) -> None:
    """Keep one open JSON row for this data type, replacing it when the payload changes."""
    datatype = _data_type(key, "json")
    current = (
        organization.to_organizationatlasdata.select_for_update().filter(
            source=source,
            country_code=country,
            data_type=datatype,
            valid_to__isnull=True,
        )
        .order_by("-created_at")
        .first()
    )
    if current is None:
        current, created = _create_open_data(
            organization=organization,
            source=source,
            country_code=country,
            data_type=datatype,
            value=value,
        )
        if created:
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


def _save_api_trace(organization, obj) -> None:
    value = _api_trace_value(obj)
    if not value:
        return
    _save_open_json_data(
        organization,
        key=_API_TRACE,
        value=value,
        source=getattr(obj, "backend", None) or "",
        country=getattr(obj, "country_code", None) or "",
    )


def _save_api_history_trace(organization, rows: list[dict], *, source: str) -> None:
    _save_open_json_data(
        organization,
        key=_API_HISTORY_TRACE,
        value=json.dumps(rows, ensure_ascii=False, default=str),
        source=source,
        country=organization.country_code or "",
    )


def _refresh_address(organization, obj) -> None:
    new_address = getattr(obj, "address_json", None)
    if not new_address:
        return
    headquarters = list(
        organization.to_organizationatlasaddress.select_for_update().filter(
            is_headquarters=True,
            valid_to__isnull=True,
        )
    )
    incoming = _address_items(new_address)
    if any(_address_items(row.address) == incoming for row in headquarters):
        return
    today = date.today()
    for row in headquarters:
        row.valid_to = (
            today
            if row.valid_from is not None and row.valid_from >= today
            else today - timedelta(days=1)
        )
        row.save(update_fields=["valid_to", "updated_at"])
    OrganizationAtlasAddress.objects.create(
        organization=organization,
        source=getattr(obj, "backend", None),
        country_code=getattr(obj, "country_code", None) or None,
        address=new_address,
        is_headquarters=True,
        valid_from=today,
    )


def _as_date(value, *, field: str):
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError as exc:
        raise OrganizationHistoryError(
            f"Invalid {field} date in organization history: {value!r}"
        ) from exc


def _history_rows_from_result(result) -> tuple[list[dict], str | None]:
    if not isinstance(result, dict):
        return [], None
    if result.get("error"):
        return [], str(result["error"])
    provider = result.get("provider")
    if provider is None:
        return [], None
    normalized = provider.get_service_normalize("get_organization_history")
    if isinstance(normalized, dict) and normalized.get("error"):
        return [], str(normalized["error"])
    if not isinstance(normalized, list):
        return [], None
    return [item for item in normalized if isinstance(item, dict)], None


def fetch_organization_history(code: str, provider_name: str) -> list[dict]:
    """Normalized history rows from the provider that implements the service."""
    if not code or not provider_name:
        return []
    results = get_organization_history(
        code,
        attribute_search={"name": provider_name},
    )
    rows: list[dict] = []
    errors: list[str] = []
    for result in results or []:
        result_rows, error = _history_rows_from_result(result)
        rows.extend(result_rows)
        if error:
            errors.append(error)
    if errors:
        raise RuntimeError("; ".join(errors))
    return rows


def _history_queryset(organization, *, source: str, country: str, datatype):
    return organization.to_organizationatlasdata.filter(
        source=source,
        country_code=country,
        data_type=datatype,
    )


def _transition_open_history_record(existing, *, value: str, valid_from: date | None) -> bool:
    open_record = existing.select_for_update().filter(valid_to__isnull=True).first()
    if open_record is None:
        return False
    if open_record.valid_from is None and valid_from is not None:
        open_record.value = value
        open_record.valid_from = valid_from
        open_record.save(update_fields=["value", "valid_from", "updated_at"])
        return True
    if valid_from is None or (
        open_record.valid_from is not None
        and valid_from <= open_record.valid_from
    ):
        raise OrganizationHistoryError(
            f"Cannot open history period at {valid_from!r} after "
            f"existing period starting at {open_record.valid_from!r}"
        )
    open_record.valid_to = valid_from - timedelta(days=1)
    open_record.save(update_fields=["valid_to", "updated_at"])
    return False


def _save_history_row(organization, row: dict, *, source: str) -> None:
    field = row.get("field")
    value = row.get("value")
    if field in (None, "") or value in (None, ""):
        return
    country = row.get("country_code") or organization.country_code or ""
    valid_from = _as_date(row.get("valid_from"), field="valid_from")
    valid_to = _as_date(row.get("valid_to"), field="valid_to")
    datatype = _data_type(str(field))
    existing = _history_queryset(
        organization, source=source, country=country, datatype=datatype
    )
    current = existing.filter(valid_from=valid_from, valid_to=valid_to).first()
    if current is None:
        if valid_to is None and _transition_open_history_record(
            existing,
            value=str(value),
            valid_from=valid_from,
        ):
            return
        OrganizationAtlasData.objects.create(
            organization=organization,
            source=source,
            country_code=country,
            data_type=datatype,
            value=str(value),
            valid_from=valid_from,
            valid_to=valid_to,
        )
        return
    current.value = str(value)
    current.valid_from = valid_from
    current.valid_to = valid_to
    current.save(update_fields=["value", "valid_from", "valid_to", "updated_at"])


@transaction.atomic
def apply_organization_history(organization, rows: list[dict], *, source: str) -> int:
    """Store historized values. Closed periods are written before the current one."""
    ordered = sorted(
        rows,
        key=lambda row: (
            row.get("valid_to") in (None, ""),
            str(row.get("field") or ""),
            str(row.get("valid_from") or ""),
        ),
    )
    count = 0
    for row in ordered:
        if row.get("field") in (None, "") or row.get("value") in (None, ""):
            continue
        _save_history_row(organization, row, source=source or row.get("backend") or "")
        count += 1
    return count


def load_organization_history(organization, provider_name: str) -> int:
    rows = fetch_organization_history(organization.code, provider_name)
    if not rows:
        return 0
    with transaction.atomic():
        _save_api_history_trace(organization, rows, source=provider_name)
        return apply_organization_history(organization, rows, source=provider_name)


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
