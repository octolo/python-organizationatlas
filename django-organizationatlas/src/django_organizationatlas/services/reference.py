import csv
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management.base import CommandError
from django.db import transaction
from django.db.models import Exists, OuterRef, Q
from django.db.models.lookups import IsNull

from django_organizationatlas.category_names import (
    category_name, category_name_expression, data_type_name,
)
from django_organizationatlas.country_codes import GLOBAL_COUNTRY_CODE
from django_organizationatlas.managers.reference import FEATURE_CATEGORY
from django_organizationatlas.models import (
    OrganizationAtlasData,
    OrganizationAtlasReference,
    OrganizationAtlasReferenceCategory,
)
from django_organizationatlas.reference_codes import normalize_reference_code
from django_organizationatlas.models.source import USER_COUNTRY_CODE
from django_organizationatlas.models.reference import category_default_unique

from .reference_csv import (
    REFERENCE_COLUMNS,
    has_reference_columns,
    is_category_csv,
    read_category_csv,
    read_csv,
)

DEFAULT_DUMP_FILENAME = "dump.csv"
REFERENCE_FIXTURE_SUFFIX = '_ref.csv'
CATEGORY_FIXTURE_SUFFIX = '_cat.csv'
DEFAULT_FIXTURE = 'organizationatlas_ref.csv'


def default_fixture_path() -> Path:
    """References organizationatlas needs in order to run."""
    return fixtures_root() / DEFAULT_FIXTURE


def load_default_references():
    """Import the default reference fixture."""
    return import_library_fixture(default_fixture_path(), REFERENCE_FIXTURE_SUFFIX)


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
        if not path.is_file() or not path.name.endswith(
            (REFERENCE_FIXTURE_SUFFIX, CATEGORY_FIXTURE_SUFFIX),
        ):
            continue
        relative = path.relative_to(root).as_posix()
        directory, _, name = relative.rpartition("/")
        rows.append({"path": relative, "directory": directory or ".", "name": name})
    return rows


def resolve_fixture(relative: str, suffix: str) -> Path:
    """Return a CSV inside fixtures/, or raise if the path leaves that directory."""
    root = fixtures_root().resolve()
    if not relative or relative.startswith(("/", "\\")) or "\\" in relative:
        raise CommandError("Unknown fixture")
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise CommandError("Unknown fixture") from exc
    if not candidate.is_file() or not candidate.name.endswith(suffix):
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


def _reconcile_data_values(category_names):
    references = OrganizationAtlasReference.objects.filter(
        category__name__in=category_names, default_value="",
    ).select_related("category")
    displays = {
        (ref.category.name, ref.category.country_code, ref.code): ref.display_code
        for ref in references
    }
    dynamic_reference = OrganizationAtlasReference.objects.filter(
        to_organizationatlasdata=OuterRef("pk"),
    ).filter(
        (
            Q(IsNull(OuterRef('data_type__category_id'), False))
            & ~Q(category_id=OuterRef('data_type__category_id'))
        )
        | (
            Q(IsNull(OuterRef('data_type__category_id'), True))
            & ~Q(category__name=OuterRef("reference_category_name"))
        )
        | Q(default_value__gt=""),
    )
    data = (
        OrganizationAtlasData.objects.filter(
            Q(data_type__category__name__in=category_names)
            | Q(
                data_type__category__isnull=True,
                data_type__data_type__in=[
                    data_type_name(name) for name in category_names
                ],
            ),
            data_type__value_type="str",
        )
        .annotate(
            reference_category_name=category_name_expression(
                'data_type__data_type',
            ),
            has_dynamic_reference=Exists(dynamic_reference),
        )
        .filter(has_dynamic_reference=False)
        .select_related("data_type__category", "organization")
        .only(
            'pk', 'value', 'country_code',
            'data_type__data_type', 'data_type__category__name',
            'data_type__category__country_code', 'organization__country_code',
        )
    )
    for row in data.iterator():
        country = row.country_code
        if not country or country == USER_COUNTRY_CODE:
            country = row.organization.country_code or ""
        category = row.data_type.category
        key = (
            category.name if category else category_name(row.data_type.data_type),
            normalize_reference_code(row.value),
        )
        if category:
            country = category.country_code
        value = displays.get((key[0], country, key[1]))
        if value is None and category is None:
            value = displays.get((key[0], GLOBAL_COUNTRY_CODE, key[1]))
        if value is not None and value != row.value:
            OrganizationAtlasData.objects.filter(pk=row.pk).update(value=value)


@transaction.atomic
def import_reference_rows(rows):
    created_count = 0
    updated_count = 0
    category_names = set()

    for row in rows:
        country = row["country_code"] or GLOBAL_COUNTRY_CODE
        category = OrganizationAtlasReferenceCategory.for_name(
            row["category"],
            country,
        )
        category_names.add(category.name)
        defaults = {
            "description": row["description"],
            "source": row["source"],
            "country_code": country,
        }
        code = normalize_reference_code(row["code"])
        existing = OrganizationAtlasReference.objects.filter(
            category=category, code=code,
        ).first()
        defaults["display_code"] = (
            row.get("display_code")
            or (existing.display_code if existing else row["code"])
        )
        if "characteristics" in row:
            defaults["characteristics"] = row["characteristics"]
        if "priority" in row:
            defaults["priority"] = row["priority"]
        if "default_value" in row:
            defaults["default_value"] = row["default_value"]
        if "source_category" in row:
            source_name = row["source_category"]
            defaults["source_category"] = (
                OrganizationAtlasReferenceCategory.for_name(source_name, country)
                if source_name
                else None
            )
        try:
            _, created = OrganizationAtlasReference.objects.update_or_create(
                category=category,
                code=code,
                defaults=defaults,
            )
        except ValidationError as error:
            raise CommandError(
                f"Invalid reference {row['category']}/{row['code']}: {error}"
            ) from error

        if created:
            created_count += 1
        else:
            updated_count += 1

    if category_names:
        _reconcile_data_values(category_names)
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


@transaction.atomic
def load_configured_features(features=None):
    """Create or update feature references from ORGANIZATIONATLAS_FEATURES."""
    created_count = 0
    updated_count = 0
    categories = {}
    for feature in configured_features() if features is None else features:
        country_code = feature["country_code"] or GLOBAL_COUNTRY_CODE
        category = categories.get(country_code)
        if category is None:
            category = OrganizationAtlasReferenceCategory.for_name(FEATURE_CATEGORY, country_code)
            categories[country_code] = category
        defaults = {"source": "settings", "country_code": country_code}
        code = normalize_reference_code(feature["code"])
        existing = OrganizationAtlasReference.objects.filter(
            category=category, code=code,
        ).first()
        defaults["display_code"] = (
            existing.display_code if existing else feature["code"]
        )
        if "description" in feature:
            defaults["description"] = feature["description"]
        try:
            _reference, created = OrganizationAtlasReference.objects.update_or_create(
                category=category,
                code=code,
                defaults=defaults,
            )
        except ValidationError as error:
            raise CommandError(
                f"Invalid feature {feature['code']!r}: {error}"
            ) from error
        if created:
            created_count += 1
        else:
            updated_count += 1
    if categories:
        _reconcile_data_values({FEATURE_CATEGORY})
    return created_count, updated_count


@transaction.atomic
def import_category_rows(rows):
    created_count = 0
    updated_count = 0
    for row in rows:
        defaults = {}
        if row['description']:
            defaults['description'] = row['description']
        if 'unique' in row:
            defaults['unique'] = row['unique']
        try:
            _, created = OrganizationAtlasReferenceCategory.objects.update_or_create(
                name=category_name(row["name"]),
                country_code=row["country_code"] or GLOBAL_COUNTRY_CODE,
                defaults=defaults,
                create_defaults={
                    'unique': category_default_unique(category_name(row['name'])),
                    **defaults,
                },
            )
        except ValidationError as error:
            raise CommandError(
                f"Invalid category {row['name']!r}: {error}"
            ) from error
        if created:
            created_count += 1
        else:
            updated_count += 1
    return created_count, updated_count


def import_csv_file(path):
    path = Path(path)
    if path.resolve().is_relative_to(fixtures_root().resolve()):
        suffix = _library_fixture_suffix(path)
        if suffix is None:
            raise CommandError('Unknown fixture type')
        return import_library_fixture(path, suffix)
    if is_category_csv(path):
        return import_category_rows(read_category_csv(path))
    return import_reference_rows(read_csv(path))


def import_library_fixture(path, suffix):
    """Import a library fixture according to its expected suffix."""
    if not path.name.endswith(suffix):
        raise CommandError('Unknown fixture')
    if suffix == CATEGORY_FIXTURE_SUFFIX:
        return import_category_rows(read_category_csv(path))
    if suffix == REFERENCE_FIXTURE_SUFFIX:
        return import_reference_rows(read_csv(path))
    raise CommandError('Unknown fixture type')


def _library_fixture_suffix(path):
    for suffix in (CATEGORY_FIXTURE_SUFFIX, REFERENCE_FIXTURE_SUFFIX):
        if path.name.endswith(suffix):
            return suffix
    return None


def import_reference_from_path(path):
    total_created = 0
    total_updated = 0
    csv_paths = get_csv_paths(path)
    importing_tree = Path(path).is_dir() or any(char in str(path) for char in "*?[")

    if not csv_paths:
        raise CommandError(f"No CSV files found in: {path}")

    imported_files = 0
    for csv_path in csv_paths:
        if csv_path.resolve().is_relative_to(fixtures_root().resolve()):
            if importing_tree and _library_fixture_suffix(csv_path) is None:
                continue
        elif (
            importing_tree
            and not is_category_csv(csv_path)
            and not has_reference_columns(csv_path)
        ):
            continue
        created_count, updated_count = import_csv_file(csv_path)
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
        writer = csv.DictWriter(
            csv_file,
            fieldnames=(*REFERENCE_COLUMNS, "display_code", "default_value"),
            delimiter=";",
        )
        writer.writeheader()

        for reference in references:
            writer.writerow(
                {
                    "category": reference.category.name,
                    "code": reference.code,
                    "description": reference.description,
                    "country_code": reference.category.country_code,
                    "source": reference.source or "",
                    "display_code": reference.display_code,
                    "default_value": reference.default_value,
                }
            )

    return dump_path, references.count()
