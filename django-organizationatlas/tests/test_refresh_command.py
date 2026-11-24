import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from unittest.mock import patch

from django_organizationatlas.models import OrganizationAtlasOrganization


def _organization(code="917432254", country="FR"):
    return OrganizationAtlasOrganization.objects.create(
        denomination="Octolo",
        code=code,
        source="insee",
        country_code=country,
    )


@pytest.mark.django_db
def test_refresh_command_uses_the_service_for_one_organization():
    organization = _organization()

    with patch(
        "django_organizationatlas.management.commands.refresh.refresh_from_providers",
        return_value={"refreshed": ["insee"], "errors": []},
    ) as refresh:
        call_command("refresh", "--code", organization.code, "--provider", "insee")

    refresh.assert_called_once_with(organization, ["insee"])


@pytest.mark.django_db
def test_refresh_command_refreshes_every_organization():
    with patch(
        "django_organizationatlas.management.commands.refresh.refresh_all_organizations",
    ) as refresh:
        call_command("refresh", "--provider", "insee")

    refresh.assert_called_once_with(["insee"])


@pytest.mark.django_db
def test_refresh_command_can_enqueue_one_organization():
    organization = _organization()

    with patch(
        "django_organizationatlas.management.commands.refresh.enqueue_refresh_one_organization",
    ) as enqueue:
        call_command(
            "refresh",
            "--enqueue",
            "--code",
            organization.code,
            "--country",
            "FR",
        )

    enqueue.assert_called_once_with(organization.pk, None)


@pytest.mark.django_db
def test_refresh_command_reports_service_errors():
    organization = _organization()

    with (
        patch(
            "django_organizationatlas.management.commands.refresh.refresh_from_providers",
            return_value={"refreshed": [], "errors": ["insee: refresh failed"]},
        ),
        pytest.raises(CommandError, match="refresh failed"),
    ):
        call_command("refresh", "--code", organization.code)


@pytest.mark.django_db
def test_refresh_command_requires_a_country_when_the_code_is_shared():
    _organization(country="FR")
    _organization(country="BE")

    with pytest.raises(CommandError, match="Pass --country"):
        call_command("refresh", "--code", "917432254")


@pytest.mark.django_db
def test_refresh_command_selects_duplicate_by_id_and_rejects_ambiguous_code():
    original = _organization()
    duplicate = OrganizationAtlasOrganization.objects.create(
        denomination='Octolo', code=original.code, source='insee',
        country_code='FR', is_duplicate=True,
    )
    with pytest.raises(CommandError, match='--organization-id'):
        call_command('refresh', '--code', original.code, '--country', 'FR')
    with patch(
        'django_organizationatlas.management.commands.refresh.refresh_from_providers',
        return_value={'refreshed': ['insee'], 'errors': []},
    ) as refresh:
        call_command('refresh', '--organization-id', str(duplicate.pk))
    refresh.assert_called_once_with(duplicate, None)
