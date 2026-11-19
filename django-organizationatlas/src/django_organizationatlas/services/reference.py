import csv
from pathlib import Path

from django.conf import settings
from django.core.management.base import CommandError

from django_organizationatlas.managers.reference import FEATURE_CATEGORY
from django_organizationatlas.models import (
    OrganizationAtlasReference,
    OrganizationAtlasReferenceCategory,
)

from .reference_csv import (
    REFERENCE_COLUMNS,
    has_reference_columns,
    is_category_csv,
    read_category_csv,
    read_csv,
)

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


def import_reference_rows(rows):
    created_count = 0
    updated_count = 0

    for row in rows:
        category = OrganizationAtlasReferenceCategory.for_name(
            row["category"],
            row["country_code"],
        )
        defaults = {
            "description": row["description"],
            "source": row["source"],
            "country_code": row["country_code"],
        }
        if "characteristics" in row:
            defaults["characteristics"] = row["characteristics"]
        if "priority" in row:
            defaults["priority"] = row["priority"]
        if "default_value" in row:
            defaults["default_value"] = row["default_value"]
        if "source_category" in row:
            source_name = row["source_category"]
            defaults["source_category"] = (
                OrganizationAtlasReferenceCategory.for_name(source_name, row["country_code"])
                if source_name
                else None
            )
        _, created = OrganizationAtlasReference.objects.update_or_create(
            category=category,
            code=row["code"],
            defaults=defaults,
        )

        if created:
            created_count += 1
        else:
            updated_count += 1

    return created_count, updated_count


def _feature_from_setting(index, item):
    label = f"ORGANIZATIONATLAS_FEATURES[{index}]"
    if isinstance(item, str):
        feature = {"code": item.strip(), "country_code": ""}
    elif isinstance(item, dict):
        feature = {
            "code": str(item.get("code") or "").strip(),
            "country_code": str(item.get("country_code") or "").strip(),
        }
        if item.get("description") is not None:
            feature["description"] = str(item["description"]).strip()
    else:
        raise CommandError(f"{label} must be a code or a mapping with a code.")
    if not feature["code"]:
        raise CommandError(f"{label} needs a code.")
    return feature


def configured_features():
    """Features declared in the ORGANIZATIONATLAS_FEATURES setting."""
    raw = getattr(settings, "ORGANIZATIONATLAS_FEATURES", None) or []
    if isinstance(raw, str) or not isinstance(raw, (list, tuple)):
        raise CommandError("ORGANIZATIONATLAS_FEATURES must be a list.")
    return [_feature_from_setting(index, item) for index, item in enumerate(raw)]


def load_configured_features(features=None):
    """Create or update feature references from ORGANIZATIONATLAS_FEATURES."""
    created_count = 0
    updated_count = 0
    categories = {}
    for feature in configured_features() if features is None else features:
        country_code = feature["country_code"]
        category = categories.get(country_code)
        if category is None:
            category = OrganizationAtlasReferenceCategory.for_name(FEATURE_CATEGORY, country_code)
            categories[country_code] = category
        defaults = {"source": "settings", "country_code": country_code}
        if "description" in feature:
            defaults["description"] = feature["description"]
        _reference, created = OrganizationAtlasReference.objects.update_or_create(
            category=category,
            code=feature["code"],
            defaults=defaults,
        )
        if created:
            created_count += 1
        else:
            updated_count += 1
    return created_count, updated_count


def import_category_rows(rows):
    created_count = 0
    updated_count = 0
    for row in rows:
        _, created = OrganizationAtlasReferenceCategory.objects.update_or_create(
            name=row["name"],
            country_code=row["country_code"],
            defaults={"description": row["description"]},
        )
        if created:
            created_count += 1
        else:
            updated_count += 1
    return created_count, updated_count


def import_csv_file(path):
    if is_category_csv(path):
        return import_category_rows(read_category_csv(path))
    return import_reference_rows(read_csv(path))


def import_reference_from_path(path):
    total_created = 0
    total_updated = 0
    csv_paths = get_csv_paths(path)
    importing_tree = Path(path).is_dir() or any(char in str(path) for char in "*?[")

    if not csv_paths:
        raise CommandError(f"No CSV files found in: {path}")

    imported_files = 0
    for csv_path in csv_paths:
        if is_category_csv(csv_path):
            created_count, updated_count = import_category_rows(read_category_csv(csv_path))
        elif has_reference_columns(csv_path):
            created_count, updated_count = import_reference_rows(read_csv(csv_path))
        elif importing_tree:
            continue
        else:
            created_count, updated_count = import_reference_rows(read_csv(csv_path))
        total_created += created_count
        total_updated += updated_count
        imported_files += 1

    if imported_files == 0:
        raise CommandError(f"No reference CSV files found in: {path}")

    return total_created, total_updated, imported_files


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
