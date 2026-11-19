import csv
from pathlib import Path

from django.core.management.base import CommandError

REFERENCE_COLUMNS = ("category", "code", "description", "country_code", "source")
REQUIRED_COLUMNS = set(REFERENCE_COLUMNS)
CATEGORY_COLUMNS = {"name", "country_code"}
_PRESENT_WHEN_COLUMN_EXISTS = ("default_value", "source_category")


def _cell(row, name):
    return (row.get(name) or "").strip()


def _require_columns(fieldnames, required):
    missing = required - fieldnames
    if not missing:
        return
    missing_list = ", ".join(sorted(missing))
    raise CommandError(f"Missing required CSV columns: {missing_list}")


def _open_reader(csv_file):
    reader = csv.DictReader(csv_file, delimiter=";")
    return reader, set(reader.fieldnames or [])


def _read_rows(csv_file, required, build_row):
    reader, fieldnames = _open_reader(csv_file)
    _require_columns(fieldnames, required)
    rows = []
    for row in reader:
        item = build_row(row, fieldnames)
        if item is not None:
            rows.append(item)
    return rows


def _add_optional_reference_fields(item, row, fieldnames):
    characteristics = _cell(row, "characteristics")
    if characteristics:
        item["characteristics"] = characteristics
    priority = _cell(row, "priority")
    if priority:
        item["priority"] = int(priority)
    for column in _PRESENT_WHEN_COLUMN_EXISTS:
        if column in fieldnames:
            item[column] = _cell(row, column)


def _reference_row(row, fieldnames):
    if not _cell(row, "code"):
        return None
    item = {column: _cell(row, column) for column in REFERENCE_COLUMNS}
    _add_optional_reference_fields(item, row, fieldnames)
    return item


def _category_row(row, _fieldnames):
    name = _cell(row, "name")
    if not name:
        return None
    return {
        "name": name,
        "country_code": _cell(row, "country_code"),
        "description": _cell(row, "description"),
    }


def read_csv_file(csv_file):
    return _read_rows(csv_file, REQUIRED_COLUMNS, _reference_row)


def read_category_csv_file(csv_file):
    return _read_rows(csv_file, CATEGORY_COLUMNS, _category_row)


def read_csv(path):
    csv_path = Path(path)
    if not csv_path.exists():
        raise CommandError(f"CSV file not found: {csv_path}")
    with csv_path.open(encoding="utf-8", newline="") as csv_file:
        return read_csv_file(csv_file)


def read_category_csv(path):
    with Path(path).open(encoding="utf-8", newline="") as csv_file:
        return read_category_csv_file(csv_file)


def csv_fieldnames(path):
    with Path(path).open(encoding="utf-8", newline="") as csv_file:
        return set(csv.DictReader(csv_file, delimiter=";").fieldnames or [])


def has_reference_columns(path) -> bool:
    return csv_fieldnames(path) >= REQUIRED_COLUMNS


def is_category_csv(path) -> bool:
    fieldnames = csv_fieldnames(path)
    return fieldnames >= CATEGORY_COLUMNS and "code" not in fieldnames
