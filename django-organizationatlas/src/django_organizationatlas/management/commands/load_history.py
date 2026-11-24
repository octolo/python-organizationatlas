from django.core.management.base import BaseCommand, CommandError

from django_organizationatlas.management.organization import selected_organization
from django_organizationatlas.services.history import load_history_from_providers
from django_organizationatlas.task.history import (
    enqueue_load_all_organization_histories,
    enqueue_load_one_organization_history,
    load_all_organization_histories,
)


class Command(BaseCommand):
    help = "Import organization history from providers"

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
                enqueue_load_one_organization_history(organization.pk, providers)
            else:
                enqueue_load_all_organization_histories(providers)
            self.stdout.write(self.style.SUCCESS("Organization history load queued."))
            return
        if code or organization_id is not None:
            organization = selected_organization(
                code, options['country'], organization_id,
            )
            result = load_history_from_providers(organization, providers)
            if result["errors"]:
                raise CommandError("; ".join(result["errors"]))
            names = ", ".join(result["processed"]) or "no provider"
            self.stdout.write(self.style.SUCCESS(f"Loaded history from {names}."))
            return
        try:
            load_all_organization_histories(providers)
        except RuntimeError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS("Loaded organization history."))
