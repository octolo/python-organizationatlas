"""History import tasks."""

from ..models import OrganizationAtlasOrganization
from ..services.history import load_history_from_providers
from . import get_task_backend
from .refresh import refresh_all_organizations


def load_all_organization_histories(provider_names=None):
    """Import history for every organization."""
    return refresh_all_organizations(provider_names, actions=['history'])


def load_one_organization_history(organization_id, provider_names=None):
    """Import history for one organization and report provider errors."""
    organization = OrganizationAtlasOrganization.objects.get(pk=organization_id)
    result = load_history_from_providers(organization, provider_names)
    if result['errors']:
        raise RuntimeError('; '.join(result['errors']))
    return result


def enqueue_load_all_organization_histories(provider_names=None):
    """Enqueue a history import for every organization."""
    return get_task_backend().enqueue(
        load_all_organization_histories,
        provider_names,
    )


def enqueue_load_one_organization_history(organization_id, provider_names=None):
    """Enqueue a history import for one organization."""
    return get_task_backend().enqueue(
        load_one_organization_history,
        organization_id,
        provider_names,
    )
