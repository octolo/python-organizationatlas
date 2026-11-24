from datetime import date

from django.urls import reverse

from ..category_names import category_name
from ..country_codes import GLOBAL_COUNTRY_CODE
from ..helpers import _TIMELINE_EXCLUDED_DATA_TYPES
from ..managers.data import start_at_expression
from ..models.reference import OrganizationAtlasReferenceCategory
from ..models.source import USER_COUNTRY_CODE


class _TimelineAddress:
    """Address row shaped like organization data so the timeline can mix both."""

    def __init__(self, address):
        self.valid_from = address.valid_from
        self.start_at = address.start_at
        self.valid_to = address.valid_to
        self.data_type = "headquarters" if address.is_headquarters else "address"
        self.value = str(address.address or "")
        self.data_reference = ""
        self.data_type_url = ""
        self._source_label = address.source_label()

    def source_label(self):
        return self._source_label


def timeline_entries(organization):
    data = (
        organization.to_organizationatlasdata.select_related(
            "data_type__category",
        )
        .with_data_reference()
        .with_start_at()
        .exclude(data_type__data_type__in=_TIMELINE_EXCLUDED_DATA_TYPES)
    )
    entries = list(data)
    category_urls = _category_urls(entries, organization)
    for row in entries:
        row.data_type_url = category_urls.get(row.pk, "")
    addresses = organization.to_organizationatlasaddress.annotate(
        start_at=start_at_expression()
    )
    for address in addresses:
        if not str(address.address or "").strip():
            continue
        entries.append(_TimelineAddress(address))
    entries.sort(
        key=lambda row: (
            row.start_at is None,
            row.start_at or date.min,
            str(row.data_type),
        )
    )
    return entries


def _category_urls(rows, organization):
    """Reference changelist filtered on the category named like the data type."""
    names = {
        row.data_type.category.name
        if row.data_type.category_id
        else category_name(str(row.data_type))
        for row in rows
    }
    if not names:
        return {}
    grouped = {}
    for category in OrganizationAtlasReferenceCategory.objects.filter(name__in=names):
        grouped.setdefault(category.name, []).append(category)
    urls = {}
    for row in rows:
        country = row.country_code
        if not country or country == USER_COUNTRY_CODE:
            country = organization.country_code or ""
        name = category_name(str(row.data_type))
        category = (
            row.data_type.category
            if row.data_type.category_id
            else _category_for_country(grouped.get(name, []), country)
        )
        urls[row.pk] = _reference_changelist_url(category.pk) if category else ""
    return urls


def _category_for_country(categories, country):
    for category in categories:
        if category.country_code == country:
            return category
    for category in categories:
        if category.country_code == GLOBAL_COUNTRY_CODE:
            return category
    return None


def _reference_changelist_url(category_id):
    url = reverse("admin:django_organizationatlas_organizationatlasreference_changelist")
    return f"{url}?category__id__exact={category_id}"


def timeline_groups(rows):
    groups = []
    current_start = object()
    current = None
    for row in rows:
        if row.start_at != current_start:
            current_start = row.start_at
            current = {"start_at": row.start_at, "rows": []}
            groups.append(current)
        current["rows"].append(row)
    return groups
