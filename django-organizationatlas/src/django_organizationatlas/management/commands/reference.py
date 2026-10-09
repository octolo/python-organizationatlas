from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from django_organizationatlas.services.reference import (
    export_reference_to_path,
    fixtures_root,
    import_reference_from_path,
)


class Command(BaseCommand):
    help = "Import or export reference CSV files"

    def add_arguments(self, parser):
        parser.add_argument(
            "--export",
            nargs="?",
            const="",
            default=None,
            help="Export reference data to a CSV file. Defaults to reference/export/dump.csv",
        )
        parser.add_argument(
            "--import",
            nargs="?",
            const="",
            default=None,
            dest="import_path",
            help=(
                "CSV file or directory to import. "
                "Defaults to the CSV files under fixtures/"
            ),
        )

    def handle(self, **options):
        export = options.get("export")
        import_path = options.get("import_path")

        if export is not None and import_path is not None:
            raise CommandError("Use either --export or --import, not both")

        if export is None and import_path is None:
            raise CommandError("Use --export or --import")

        if export is not None:
            path = export or Path.cwd() / "reference" / "export"
            dump_path, exported_count = export_reference_to_path(path)
            self.stdout.write(
                self.style.SUCCESS(f"Exported {exported_count} reference row(s) to {dump_path}")
            )
            return

        path = import_path or fixtures_root()
        created_count, updated_count, file_count = import_reference_from_path(path)
        self.stdout.write(
            self.style.SUCCESS(
                f"Imported {file_count} file(s): {created_count} created, {updated_count} updated"
            )
        )
