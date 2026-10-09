import csv
from pathlib import Path

from django.core.management.base import CommandError

from django_organizationatlas.models import (
    OrganizationAtlasReference,
    OrganizationAtlasReferenceCategory,
)

REFERENCE_COLUMNS = ("category", "code", "description", "country_code", "source")
REQUIRED_COLUMNS = set(REFERENCE_COLUMNS)
DEFAULT_DUMP_FILENAME = "dump.csv"


def fixtures_root() -> Path:
    """CSV library shipped with the package, under fixtures/."""
    return Path(__file__).resolve().parents[1] / "fixtures"


def list_fixtures() -> list[dict]:
    """CSV files under fixtures/, relative to that directory."""
    root = fixtures_root()
    if not root.is_dir():
        return []
    rows = []
    for path in sorted(root.rglob("*.csv")):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        directory, _, name = relative.rpartition("/")
        rows.append({"path": relative, "directory": directory or ".", "name": name})
    return rows


def resolve_fixture(relative: str) -> Path:
    """Return a CSV inside fixtures/, or raise if the path leaves that directory."""
    root = fixtures_root().resolve()
    if not relative or relative.startswith(("/", "\\")) or "\\" in relative:
        raise CommandError("Unknown fixture")
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise CommandError("Unknown fixture") from exc
    if not candidate.is_file() or candidate.suffix.lower() != ".csv":
        raise CommandError("Unknown fixture")
    return candidate


def get_csv_paths(path):
    if path is None:
        raise CommandError("A path is required")

    csv_path = Path(path)

    if any(char in str(csv_path) for char in "*?["):
        return sorted(csv_path.parent.glob(csv_path.name))

    if csv_path.is_dir():
        return sorted(path for path in csv_path.rglob("*.csv") if path.is_file())

    if not csv_path.exists():
        return []

    return [csv_path]


def get_dump_path(path):
    dump_path = Path(path)

    if dump_path.suffix.lower() == ".csv":
        dump_path.parent.mkdir(parents=True, exist_ok=True)
        return dump_path

    dump_path.mkdir(parents=True, exist_ok=True)
    return dump_path / DEFAULT_DUMP_FILENAME


def read_csv(path):
    csv_path = Path(path)

    if not csv_path.exists():
        raise CommandError(f"CSV file not found: {csv_path}")

    with csv_path.open(encoding="utf-8", newline="") as csv_file:
        return read_csv_file(csv_file)


def read_csv_file(csv_file):
    rows = []
    reader = csv.DictReader(csv_file, delimiter=";")
    fieldnames = set(reader.fieldnames or [])
    missing_columns = REQUIRED_COLUMNS - fieldnames

    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise CommandError(f"Missing required CSV columns: {missing}")

    for row in reader:
        if not row.get("code"):
            continue

        rows.append(
            {
                "category": row["category"].strip(),
                "code": row["code"].strip(),
                "description": row["description"].strip(),
                "country_code": row["country_code"].strip(),
                "source": row["source"].strip(),
            }
        )

    return rows


def import_reference_rows(rows):
    created_count = 0
    updated_count = 0

    for row in rows:
        category = OrganizationAtlasReferenceCategory.for_name(
            row["category"],
            row["country_code"],
        )
        _, created = OrganizationAtlasReference.objects.update_or_create(
            category=category,
            code=row["code"],
            defaults={
                "description": row["description"],
                "source": row["source"],
                "country_code": row["country_code"],
            },
        )

        if created:
            created_count += 1
        else:
            updated_count += 1

    return created_count, updated_count


def import_reference_from_path(path):
    total_created = 0
    total_updated = 0
    csv_paths = get_csv_paths(path)

    if not csv_paths:
        raise CommandError(f"No CSV files found in: {path}")

    for csv_path in csv_paths:
        created_count, updated_count = import_reference_rows(read_csv(csv_path))
        total_created += created_count
        total_updated += updated_count

    return total_created, total_updated, len(csv_paths)


def export_reference_to_path(path):
    dump_path = get_dump_path(path)
    references = OrganizationAtlasReference.objects.select_related("category").order_by(
        "category__country_code",
        "category__name",
        "code",
    )

    with dump_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=REFERENCE_COLUMNS, delimiter=";")
        writer.writeheader()

        for reference in references:
            writer.writerow(
                {
                    "category": reference.category.name,
                    "code": reference.code,
                    "description": reference.description,
                    "country_code": reference.category.country_code,
                    "source": reference.source or "",
                }
            )

    return dump_path, references.count()
