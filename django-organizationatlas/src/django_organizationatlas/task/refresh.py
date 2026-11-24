"""Refresh tasks."""

import logging

from ..models import OrganizationAtlasOrganization
from ..services.refresh import (
    load_history_from_providers,
    refresh_from_providers,
)
from . import get_task_backend

logger = logging.getLogger(__name__)


def _validate_actions(actions):
    actions = ['refresh'] if actions is None else actions
    if not actions or set(actions) - {'refresh', 'history'}:
        raise ValueError('Choose refresh and/or history.')
    return actions


def refresh_all_organizations(provider_names=None, actions=None):
    """Run selected operations for all organizations."""
    actions = _validate_actions(actions)
    failures = []
    for organization in OrganizationAtlasOrganization.objects.iterator():
        try:
            errors = []
            history_cache = {}
            if 'refresh' in actions:
                result = refresh_from_providers(
                    organization,
                    provider_names,
                    history_cache=history_cache,
                )
                errors.extend(result['errors'])
                if not result['refreshed'] and not result['errors']:
                    errors.append('No provider refreshed the organization')
            if 'history' in actions:
                result = load_history_from_providers(
                    organization,
                    provider_names,
                    history_cache=history_cache,
                )
                errors.extend(result['errors'])
        except Exception:
            logger.exception('Organization %s refresh failed', organization.pk)
            failures.append(organization.pk)
            continue
        if errors:
            failures.append(organization.pk)
            logger.error(
                'Organization %s was not fully refreshed: %s',
                organization.pk,
                errors,
            )
    if failures:
        raise RuntimeError(f'Failed to refresh {len(failures)} organization(s)')


def refresh_one_organization(organization_id, provider_names=None):
    """Refresh one organization and report provider errors."""
    organization = OrganizationAtlasOrganization.objects.get(pk=organization_id)
    result = refresh_from_providers(organization, provider_names)
    if result['errors'] or not result['refreshed']:
        details = result['errors'] or ['No provider refreshed the organization']
        raise RuntimeError('; '.join(details))
    return result


def enqueue_refresh_all_organizations(provider_names=None, actions=None):
    """Enqueue selected operations for every organization."""
    return get_task_backend().enqueue(
        refresh_all_organizations,
        provider_names,
        _validate_actions(actions),
    )


def enqueue_refresh_one_organization(organization_id, provider_names=None):
    """Enqueue a refresh for one organization."""
    return get_task_backend().enqueue(
        refresh_one_organization,
        organization_id,
        provider_names,
    )
