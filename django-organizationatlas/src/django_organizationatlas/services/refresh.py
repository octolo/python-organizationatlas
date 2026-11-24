"""Refresh organizations from multiple providers."""

import json
import logging
from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from providerkit.helpers import get_providerkit

from ..category_names import category_name
from ..helpers import (
    _address_items,
    _as_date,
    _data_type,
    _incoming_data,
    _save_api_history_trace,
    _save_api_trace,
    _sync_provider_reference,
    apply_organization_history,
    fetch_organization_for_refresh,
    fetch_organization_history,
)
from ..models import (
    OrganizationAtlasAddress,
    OrganizationAtlasData,
    OrganizationAtlasOrganization,
)
from ..models.data import reference_value
from ..models.source import USER_COUNTRY_CODE

logger = logging.getLogger(__name__)
_DATE_KEY = 'provider_valid_from'
_DATE_VALUE_KEY = 'provider_valid_value'
_HEADQUARTERS_KEY = 'provider_headquarters'
_OBSERVATIONS_KEY = 'provider_observations'


def _observation_rank(item, priorities):
    source, observation = item
    valid_from = _as_date(observation.get('valid_from'), field=_DATE_KEY)
    return (
        valid_from is not None,
        valid_from or date.min,
        priorities.get(source, 0),
        source,
    )


def _observations(current, rows):
    observations = dict((current.metadata or {}).get(_OBSERVATIONS_KEY, {}))
    if observations:
        return observations
    for row in rows:
        metadata = row.metadata or {}
        valid_from = (
            metadata.get(_DATE_KEY)
            if metadata.get(_DATE_VALUE_KEY) == row.value
            else None
        )
        observations[row.source] = {
            'value': row.value,
            'valid_from': valid_from,
        }
    return observations


def _history_date_for_value(field, value, country, datatype, dates):
    matches = []
    for (history_field, history_value), valid_from in dates.items():
        if history_field != field:
            continue
        if history_value == value:
            matches.append(valid_from)
        elif datatype.value_type == 'str':
            history_value = reference_value(
                field, country, history_value,
                category_id=datatype.category_id,
            )
            if history_value == value:
                matches.append(valid_from)
    return max(matches, default=None)


def _save_merged_data(
    organization, datatype, country, rows, observations, priorities
):
    source, winner = max(
        observations.items(),
        key=lambda item: _observation_rank(item, priorities),
    )
    current = rows[0] if rows else None
    if any(row.source == source for row in rows[1:]):
        raise ValidationError(
            f'Existing {datatype.data_type} rows conflict with merging.'
        )
    metadata = dict(current.metadata or {}) if current else {}
    metadata[_OBSERVATIONS_KEY] = observations
    metadata.pop(_DATE_KEY, None)
    metadata.pop(_DATE_VALUE_KEY, None)
    if winner['valid_from']:
        metadata[_DATE_KEY] = winner['valid_from']
        metadata[_DATE_VALUE_KEY] = winner['value']
    if not current:
        current = OrganizationAtlasData.objects.create(
            organization=organization,
            data_type=datatype,
            country_code=country,
            source=source,
            value=winner['value'],
            metadata=metadata,
        )
        _sync_provider_reference(current)
        return
    current_day = current.valid_from or current.created_at.date()
    if current.value != winner['value'] and current_day < date.today():
        current.valid_to = date.today() - timedelta(days=1)
        current.save(update_fields=['valid_to', 'updated_at'])
        current = OrganizationAtlasData.objects.create(
            organization=organization,
            data_type=datatype,
            country_code=country,
            source=source,
            value=winner['value'],
            valid_from=date.today(),
            metadata=metadata,
        )
        _sync_provider_reference(current)
        return
    changed = (
        current.value != winner['value']
        or current.source != source
        or (current.metadata or {}) != metadata
    )
    if changed:
        previous_value = current.value
        current.value = winner['value']
        current.source = source
        current.metadata = metadata
        current.save(update_fields=['value', 'source', 'metadata', 'updated_at'])
        _sync_provider_reference(current, previous_value)
    else:
        _sync_provider_reference(current)


def _provider_value(field, country, datatype, rows, raw_value):
    if datatype.value_type != 'str':
        return raw_value
    value = reference_value(
        field, country, raw_value, category_id=datatype.category_id,
    )
    if not rows:
        return value
    current = rows[0]
    normalized = reference_value(
        field, country, current.value, category_id=datatype.category_id,
    )
    category_filter = (
        Q(category_id=datatype.category_id)
        if datatype.category_id
        else Q(category__name=category_name(field))
    )
    if (
        (raw_value != value or normalized != current.value)
        and current.reference.filter(
            ~category_filter | Q(default_value__gt='')
        ).exists()
    ):
        return raw_value
    return value


def _merge_field(organization, country, field, incoming, priorities):
    lookup_country = (
        organization.country_code or ''
        if country in ('', USER_COUNTRY_CODE)
        else country
    )
    datatype = _data_type(field, country=lookup_country)
    rows = list(
        organization.to_organizationatlasdata.select_for_update()
        .filter(
            country_code=country,
            data_type=datatype,
        )
        .active()
        .order_by('pk')
    )
    rows.sort(
        key=lambda row: (
            bool((row.metadata or {}).get(_OBSERVATIONS_KEY)),
            _rank(row, priorities),
        ),
        reverse=True,
    )
    observations = _observations(rows[0], rows) if rows else {}
    for source, raw_value, dates in incoming:
        value = _provider_value(
            field, lookup_country, datatype, rows, raw_value
        )
        previous = observations.get(source, {})
        valid_from = _history_date_for_value(
            field, value, lookup_country, datatype, dates
        )
        if not valid_from and previous.get('value') == value:
            valid_from = previous.get('valid_from')
        observations[source] = {'value': value, 'valid_from': valid_from}
    _save_merged_data(
        organization, datatype, country, rows, observations, priorities
    )


def _upsert_merged_data(organization, results, priorities):
    fields = {}
    for obj, history in results:
        country = getattr(obj, 'country_code', None) or ''
        dates = _history_dates(history)
        for field, raw_value in _incoming_data(obj).items():
            fields.setdefault((country, field), []).append(
                (obj.backend, raw_value, dates)
            )
    for (country, field), incoming in fields.items():
        _merge_field(organization, country, field, incoming, priorities)


def _priorities():
    priorities = {}
    for provider in available_providers():
        priority = getattr(provider, 'priority', 0) or 0
        priorities[provider.name] = priority
        priorities[getattr(provider, 'display_name', None) or provider.name] = (
            priority
        )
    return priorities


def available_providers():
    """Return concrete providers supporting refresh or history."""
    providers = get_providerkit().get_providers(lib_name='organizationatlas')
    if isinstance(providers, dict):
        providers = providers.values()
    return sorted(
        (
            provider
            for provider in providers
            if callable(
                getattr(provider, 'search_organization_by_reference', None)
            )
            or callable(getattr(provider, 'get_organization_history', None))
        ),
        key=lambda provider: (
            -(getattr(provider, 'priority', 0) or 0),
            provider.name,
        ),
    )


def _selected_providers(organization, names):
    providers = available_providers()
    by_name = {provider.name: provider for provider in providers}
    unknown = set(names or ()) - by_name.keys()
    if unknown:
        raise ValidationError(
            f'Unknown providers: {", ".join(sorted(unknown))}'
        )
    return [
        provider
        for provider in providers
        if (not names or provider.name in names)
        and (
            not organization.country_code
            or str(getattr(provider, 'geo_code', 'WW')).upper()
            in (
                organization.country_code.upper(),
                'WW',
            )
        )
    ]


def _provider_source(organization, provider):
    display = getattr(provider, 'display_name', None) or provider.name
    if display == provider.name:
        return display
    names = {provider.name, display}
    sources = set(
        organization.to_organizationatlasdata.filter(source__in=names)
        .values_list('source', flat=True)
        .distinct()
    )
    sources.update(
        organization.to_organizationatlasaddress.filter(source__in=names)
        .values_list('source', flat=True)
        .distinct()
    )
    for metadata in organization.to_organizationatlasdata.values_list(
        'metadata', flat=True
    ):
        sources.update(
            names.intersection((metadata or {}).get(_OBSERVATIONS_KEY, {}))
        )
    if len(sources) > 1:
        raise ValidationError(
            f'Provider {provider.name} has conflicting source labels.'
        )
    return next(iter(sources), display)


def _history_dates(rows):
    result = {}
    for row in rows:
        if row.get('valid_to') or not row.get('field') or not row.get('value'):
            continue
        start = _as_date(row.get('valid_from'), field='valid_from')
        if start is not None:
            key = (str(row['field']), str(row['value']))
            result[key] = max(result.get(key, ''), start.isoformat())
    return result


def _update_source_dates(
    organization, source, country, incoming, previous, dates
):
    rows = organization.to_organizationatlasdata.filter(
        source=source,
        country_code=country,
        data_type__data_type__in=incoming,
    ).active().select_related('data_type')
    for row in rows:
        field = row.data_type.data_type
        metadata = dict(row.metadata or {})
        if previous.get(field) != row.value:
            metadata.pop(_DATE_KEY, None)
            metadata.pop(_DATE_VALUE_KEY, None)
        source_date = _history_date_for_value(
            field, row.value, country, row.data_type, dates
        )
        if source_date:
            metadata[_DATE_KEY] = source_date
            metadata[_DATE_VALUE_KEY] = row.value
            observations = dict(metadata.get(_OBSERVATIONS_KEY, {}))
            observation = observations.get(source)
            if observation and observation.get('value') == row.value:
                observations[source] = {
                    **observation,
                    'valid_from': source_date,
                }
                metadata[_OBSERVATIONS_KEY] = observations
        if metadata != (row.metadata or {}):
            row.metadata = metadata
            row.save(update_fields=['metadata', 'updated_at'])


def _rank(row, priorities):
    value = (row.metadata or {}).get(_DATE_KEY)
    current = (
        row.value
        if isinstance(row, OrganizationAtlasData)
        else _address_items(row.address)
    )
    if (row.metadata or {}).get(_DATE_VALUE_KEY) != current:
        value = None
    start = _as_date(value, field=_DATE_KEY) if value else None
    return (
        start is not None,
        start or date.min,
        priorities.get(row.source, 0),
        -row.pk,
    )


def _address_date(obj, rows):
    dates = []
    for row in rows:
        if row.get('valid_to') or row.get('field') not in (
            'address',
            'address_json',
        ):
            continue
        value = row.get('value')
        if value in (None, ''):
            continue
        if row['field'] == 'address_json' and isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                continue
        matches = (
            value == getattr(obj, 'address', None)
            if row['field'] == 'address'
            else _address_items(value) == _address_items(obj.address_json)
        )
        if matches:
            start = _as_date(row.get('valid_from'), field='valid_from')
            if start is not None:
                dates.append(start.isoformat())
    return max(dates) if dates else None


def _upsert_address(organization, obj, history):
    incoming = getattr(obj, 'address_json', None)
    if not incoming:
        return
    source = getattr(obj, 'backend', None) or ''
    country = getattr(obj, 'country_code', None) or ''
    source_date = _address_date(obj, history)
    candidates = (
        organization.to_organizationatlasaddress.select_for_update()
        .filter(
            source=source,
            country_code=country,
            valid_to__isnull=True,
        )
        .filter(
            Q(is_headquarters=True) | Q(metadata__provider_headquarters=True)
        )
    )
    current = candidates.order_by('-created_at').first()
    if current and _address_items(current.address) == _address_items(incoming):
        metadata = {**(current.metadata or {}), _HEADQUARTERS_KEY: True}
        if source_date:
            metadata[_DATE_KEY] = source_date
            metadata[_DATE_VALUE_KEY] = _address_items(incoming)
        if metadata != (current.metadata or {}):
            current.metadata = metadata
            current.save(update_fields=['metadata', 'updated_at'])
        return
    today = date.today()
    if current and current.valid_from and current.valid_from >= today:
        current.address = incoming
        current.metadata = {**(current.metadata or {}), _HEADQUARTERS_KEY: True}
        current.metadata.pop(_DATE_KEY, None)
        current.metadata.pop(_DATE_VALUE_KEY, None)
        if source_date:
            current.metadata[_DATE_KEY] = source_date
            current.metadata[_DATE_VALUE_KEY] = _address_items(incoming)
        current.save(update_fields=['address', 'metadata', 'updated_at'])
        return
    if current:
        current.valid_to = today - timedelta(days=1)
        current.is_headquarters = False
        current.save(
            update_fields=['valid_to', 'is_headquarters', 'updated_at']
        )
    metadata = {_HEADQUARTERS_KEY: True}
    if source_date:
        metadata[_DATE_KEY] = source_date
        metadata[_DATE_VALUE_KEY] = _address_items(incoming)
    OrganizationAtlasAddress.objects.create(
        organization=organization,
        source=source,
        country_code=country,
        address=incoming,
        is_headquarters=False,
        valid_from=today,
        metadata=metadata,
    )


def preferred_data(organization, priorities=None):
    """Return preferred current data rows keyed by country and data type."""
    if priorities is None:
        priorities = _priorities()
    rows = organization.to_organizationatlasdata.active().exclude(
        data_type__data_type__in=['apitrace', 'apihistorytrace'],
    )
    result = {}
    for row in rows.select_related('data_type'):
        key = (row.country_code, row.data_type.data_type)
        if key not in result or _rank(row, priorities) > _rank(
            result[key],
            priorities,
        ):
            result[key] = row
    return result


def _choose_current(organization, priorities):
    best = max(
        (
            row for (country, field), row in
            preferred_data(organization, priorities).items()
            if field == 'denomination'
        ),
        key=lambda row: _rank(row, priorities),
        default=None,
    )
    if best is not None and organization.denomination != best.value:
        organization.denomination = best.value
        organization.save(update_fields=['denomination', 'updated_at'])
    addresses = list(
        organization.to_organizationatlasaddress.filter(
            valid_to__isnull=True,
        ).filter(
            Q(is_headquarters=True) | Q(metadata__provider_headquarters=True)
        )
    )
    if not addresses:
        return
    best = max(addresses, key=lambda row: _rank(row, priorities))
    for address in addresses:
        if address.is_headquarters and address.pk != best.pk:
            address.is_headquarters = False
            address.metadata = {
                **(address.metadata or {}),
                _HEADQUARTERS_KEY: True,
            }
            address.save(
                update_fields=['is_headquarters', 'metadata', 'updated_at']
            )
    if not best.is_headquarters:
        best.is_headquarters = True
        best.save(update_fields=['is_headquarters', 'updated_at'])


@transaction.atomic
def _apply_provider(organization, provider, obj, history):
    OrganizationAtlasOrganization.objects.select_for_update().get(
        pk=organization.pk
    )
    source = _provider_source(organization, provider)
    obj.backend = source
    _save_api_trace(organization, obj)
    if history:
        _save_api_history_trace(organization, history, source=source)
    _upsert_address(organization, obj, history)


def refresh_from_providers(
    organization, provider_names=None, *, history_cache=None
):
    """Refresh each selected provider and return results and errors."""
    providers = _selected_providers(organization, provider_names)
    priorities = _priorities()
    providers = [
        provider
        for provider in providers
        if callable(getattr(provider, 'search_organization_by_reference', None))
    ]
    selected = {provider.name for provider in providers}
    errors = [
        f'{name}: provider unavailable for refresh or country'
        for name in (provider_names or ())
        if name not in selected
    ]
    fetched = []
    code = organization.code
    if not providers:
        return {
            'refreshed': [],
            'errors': errors or ['No applicable providers available'],
        }
    for provider in providers:
        try:
            obj = fetch_organization_for_refresh(code, provider.name)
            if obj is None or not (
                getattr(obj, 'denomination', None)
                or getattr(obj, 'reference', None)
            ):
                errors.append(f'{provider.name}: no organization found')
                continue
            identifiers = {
                str(getattr(obj, name, '') or '').strip().upper()
                for name in ('reference', 'siren', 'siret', 'rna')
            }
            if code.strip().upper() not in identifiers:
                errors.append(
                    f'{provider.name}: organization identifier mismatch'
                )
                continue
            history = []
            if callable(getattr(provider, 'get_organization_history', None)):
                try:
                    if (
                        history_cache is not None
                        and provider.name in history_cache
                    ):
                        history = history_cache[provider.name]
                    else:
                        history = fetch_organization_history(
                            code, provider.name
                        )
                        if history_cache is not None:
                            history_cache[provider.name] = history
                except Exception:
                    logger.exception(
                        'History fetch failed for organization %s and provider %s',
                        organization.pk,
                        provider.name,
                    )
                    errors.append(f'{provider.name}: history failed')
                    if history_cache is not None:
                        history_cache[provider.name] = []
            fetched.append((provider, obj, history))
        except Exception:
            logger.exception(
                'Organization refresh failed for organization %s and provider %s',
                organization.pk,
                provider.name,
            )
            errors.append(f'{provider.name}: refresh failed')
    refreshed = []
    if fetched:
        try:
            refreshed = _apply_refresh_results(
                organization, fetched, priorities, errors
            )
        except Exception:
            logger.exception(
                'Organization merge failed for organization %s',
                organization.pk,
            )
            errors.append('Organization merge failed')
    return {'refreshed': refreshed, 'errors': errors}


def _apply_refresh_results(organization, fetched, priorities, errors):
    refreshed = []
    results = []
    with transaction.atomic():
        OrganizationAtlasOrganization.objects.select_for_update().get(
            pk=organization.pk,
        )
        for provider, obj, history in fetched:
            try:
                _apply_provider(organization, provider, obj, history)
            except Exception:
                logger.exception(
                    'Organization refresh failed for organization %s and provider %s',
                    organization.pk,
                    provider.name,
                )
                errors.append(f'{provider.name}: refresh failed')
                continue
            refreshed.append(provider.name)
            results.append((obj, history))
        if results:
            _upsert_merged_data(organization, results, priorities)
            _choose_current(organization, priorities)
    return refreshed


def _merge_history_observation(organization, source, row, priorities):
    country = row.get('country_code') or organization.country_code or ''
    candidates = list(
        organization.to_organizationatlasdata.select_for_update()
        .filter(
            country_code=country,
            data_type__data_type=row['field'],
        )
        .active()
        .select_related('data_type')
        .order_by('pk')
    )
    merged = next(
        (
            candidate
            for candidate in candidates
            if source in (candidate.metadata or {}).get(_OBSERVATIONS_KEY, {})
        ),
        None,
    )
    if merged is None:
        return False
    observations = dict(merged.metadata[_OBSERVATIONS_KEY])
    value = str(row['value'])
    if merged.data_type.value_type == 'str':
        value = reference_value(
            row['field'], country, value,
            category_id=merged.data_type.category_id,
        )
    if observations[source]['value'] != value:
        raise ValidationError(
            f'History conflicts with observed {row["field"]} data.'
        )
    valid_from = _as_date(row.get('valid_from'), field='valid_from')
    if valid_from:
        observations[source] = {
            **observations[source],
            'valid_from': valid_from.isoformat(),
        }
        candidates.remove(merged)
        _save_merged_data(
            organization,
            merged.data_type,
            country,
            [merged, *candidates],
            observations,
            priorities,
        )
    else:
        return merged.source != source
    winner = max(
        observations.items(),
        key=lambda item: _observation_rank(item, priorities),
    )[0]
    return winner != source


@transaction.atomic
def _apply_provider_history(organization, provider, rows):
    OrganizationAtlasOrganization.objects.select_for_update().get(
        pk=organization.pk
    )
    source = _provider_source(organization, provider)
    priorities = _priorities()
    skipped = set()
    for row in rows:
        if row.get('valid_to') or not row.get('field') or not row.get('value'):
            continue
        if _merge_history_observation(organization, source, row, priorities):
            skipped.add(id(row))
            continue
        country = row.get('country_code') or organization.country_code or ''
        current = (
            OrganizationAtlasData.objects.select_for_update()
            .filter(
                organization=organization,
                source=source,
                country_code=country,
                data_type__data_type=row['field'],
            )
            .active()
            .select_related('data_type')
            .first()
        )
        if current is None:
            continue
        value = str(row['value'])
        if current.data_type.value_type == 'str':
            value = reference_value(
                row['field'], country, value,
                category_id=current.data_type.category_id,
            )
        start = _as_date(row.get('valid_from'), field='valid_from')
        if current.value != value:
            if (
                not start
                or not current.valid_from
                or start <= current.valid_from
            ):
                raise ValidationError(
                    f'History conflicts with current {row["field"]} data.'
                )
            continue
        if (
            start is not None
            and current.valid_from
            and start < current.valid_from
        ):
            current.valid_from = start
            current.save(update_fields=['valid_from', 'updated_at'])
    apply_organization_history(
        organization,
        [row for row in rows if id(row) not in skipped],
        source=source,
    )
    _save_api_history_trace(organization, rows, source=source)
    current = OrganizationAtlasData.objects.filter(
        organization=organization,
        source=source,
    ).active().select_related('data_type')
    countries = {row.country_code for row in current}
    for country in countries:
        rows_for_country = [
            row for row in current if row.country_code == country
        ]
        values = {
            row.data_type.data_type: row.value for row in rows_for_country
        }
        _update_source_dates(
            organization,
            source,
            country,
            values,
            values,
            _history_dates(rows),
        )


def load_history_from_providers(
    organization, provider_names=None, *, history_cache=None
):
    """Import available provider history and return processed providers and errors."""
    providers = _selected_providers(organization, provider_names)
    capable = [
        provider
        for provider in providers
        if callable(getattr(provider, 'get_organization_history', None))
    ]
    if not capable:
        return {
            'processed': [],
            'errors': ['No applicable providers support organization history'],
        }
    processed = []
    errors = []
    for provider in capable:
        try:
            if history_cache is not None and provider.name in history_cache:
                rows = history_cache[provider.name]
            else:
                rows = fetch_organization_history(
                    organization.code, provider.name
                )
                if history_cache is not None:
                    history_cache[provider.name] = rows
            if rows:
                _apply_provider_history(organization, provider, rows)
            processed.append(provider.name)
        except Exception:
            logger.exception(
                'History import failed for organization %s and provider %s',
                organization.pk,
                provider.name,
            )
            errors.append(f'{provider.name}: history import failed')
    return {'processed': processed, 'errors': errors}
