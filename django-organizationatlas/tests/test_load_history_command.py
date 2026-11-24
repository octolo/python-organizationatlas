import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from unittest.mock import patch

from django_organizationatlas.models import OrganizationAtlasOrganization
from django_organizationatlas.task.history import load_all_organization_histories


def _organization(code="917432254", country="FR"):
    return OrganizationAtlasOrganization.objects.create(
        denomination="Octolo",
        code=code,
        source="insee",
        country_code=country,
    )


def test_history_task_selects_the_history_action():
    with patch(
        "django_organizationatlas.task.history.refresh_all_organizations",
    ) as refresh:
        load_all_organization_histories(["insee"])

    refresh.assert_called_once_with(["insee"], actions=["history"])


@pytest.mark.django_db
def test_load_history_command_uses_the_service_for_one_organization():
    organization = _organization()

    with patch(
        "django_organizationatlas.management.commands.load_history.load_history_from_providers",
        return_value={"processed": ["insee"], "errors": []},
    ) as load:
        call_command("load_history", "--code", organization.code, "--provider", "insee")

    load.assert_called_once_with(organization, ["insee"])


@pytest.mark.django_db
def test_load_history_command_loads_every_organization():
    with patch(
        "django_organizationatlas.management.commands.load_history.load_all_organization_histories",
    ) as load:
        call_command("load_history", "--provider", "insee")

    load.assert_called_once_with(["insee"])


@pytest.mark.django_db
def test_load_history_command_can_enqueue_one_organization():
    organization = _organization()

    with patch(
        "django_organizationatlas.management.commands.load_history.enqueue_load_one_organization_history",
    ) as enqueue:
        call_command(
            "load_history",
            "--enqueue",
            "--code",
            organization.code,
            "--country",
            "FR",
        )

    enqueue.assert_called_once_with(organization.pk, None)


@pytest.mark.django_db
def test_load_history_command_reports_service_errors():
    organization = _organization()

    with (
        patch(
            "django_organizationatlas.management.commands.load_history.load_history_from_providers",
            return_value={"processed": [], "errors": ["insee: history import failed"]},
        ),
        pytest.raises(CommandError, match="history import failed"),
    ):
        call_command("load_history", "--code", organization.code)


@pytest.mark.django_db
def test_load_history_command_requires_a_country_when_the_code_is_shared():
    _organization(country="FR")
    _organization(country="BE")

    with pytest.raises(CommandError, match="Pass --country"):
        call_command("load_history", "--code", "917432254")


@pytest.mark.django_db
def test_history_command_can_enqueue_a_duplicate_by_id():
    original = _organization()
    duplicate = OrganizationAtlasOrganization.objects.create(
        denomination='Octolo', code=original.code, source='insee',
        country_code='FR', is_duplicate=True,
    )
    with pytest.raises(CommandError, match='--organization-id'):
        call_command('load_history', '--code', original.code, '--country', 'FR')
    with patch(
        'django_organizationatlas.management.commands.load_history.'
        'enqueue_load_one_organization_history',
    ) as enqueue:
        call_command(
            'load_history', '--enqueue', '--organization-id', str(duplicate.pk),
        )
    enqueue.assert_called_once_with(duplicate.pk, None)
