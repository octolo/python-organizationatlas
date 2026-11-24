"""Resolve organizations selected by management commands."""

from django.core.management.base import CommandError

from django_organizationatlas.models import OrganizationAtlasOrganization


def selected_organization(code, country, organization_id):
    """Resolve a single organization, rejecting ambiguous codes."""
    if organization_id is not None:
        if country is not None:
            raise CommandError(
                '--country cannot be used with --organization-id.'
            )
        organization = OrganizationAtlasOrganization.objects.filter(
            pk=organization_id,
        ).first()
        if organization is None:
            raise CommandError(
                f'No organization found for ID {organization_id}.'
            )
        return organization
    queryset = OrganizationAtlasOrganization.objects.filter(code=code)
    if country is not None:
        queryset = queryset.filter(country_code=country)
    matches = list(queryset[:2])
    if not matches:
        raise CommandError(f'No organization found for code {code}.')
    if len(matches) > 1:
        raise CommandError(
            f'Several organizations use code {code}. '
            'Pass --country or --organization-id.',
        )
    return matches[0]
