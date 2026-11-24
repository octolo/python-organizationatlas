from django.core.management.base import BaseCommand, CommandError

from django_organizationatlas.management.organization import selected_organization
from django_organizationatlas.services.refresh import refresh_from_providers
from django_organizationatlas.task.refresh import (
    enqueue_refresh_all_organizations,
    enqueue_refresh_one_organization,
    refresh_all_organizations,
)


class Command(BaseCommand):
    help = "Refresh organizations from providers"

    def add_arguments(self, parser):
        parser.add_argument(
            "--provider",
            action="append",
            dest="providers",
            help="Provider name. Repeat to select several. Defaults to every applicable provider.",
        )
        selector = parser.add_mutually_exclusive_group()
        selector.add_argument(
            "--code",
            help="Organization code. Defaults to every organization.",
        )
        selector.add_argument(
            '--organization-id',
            type=int,
            help='Select a specific organization by database ID.',
        )
        parser.add_argument(
            "--country",
            help="Country code, required when several organizations share the code.",
        )
        parser.add_argument(
            "--enqueue",
            action="store_true",
            help="Run through the configured task backend instead of immediately.",
        )

    def handle(self, **options):
        providers = options["providers"] or None
        code = options["code"]
        organization_id = options['organization_id']
        if options["enqueue"]:
            if code or organization_id is not None:
                organization = selected_organization(
                    code, options['country'], organization_id,
                )
                enqueue_refresh_one_organization(organization.pk, providers)
            else:
                enqueue_refresh_all_organizations(providers)
            self.stdout.write(self.style.SUCCESS("Organization refresh queued."))
            return
        if code or organization_id is not None:
            organization = selected_organization(
                code, options['country'], organization_id,
            )
            result = refresh_from_providers(organization, providers)
            if result["errors"] or not result["refreshed"]:
                details = result["errors"] or ["No provider refreshed the organization"]
                raise CommandError("; ".join(details))
            names = ", ".join(result["refreshed"])
            self.stdout.write(self.style.SUCCESS(f"Refreshed from {names}."))
            return
        try:
            refresh_all_organizations(providers)
        except RuntimeError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS("Refreshed organizations."))
