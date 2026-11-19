from datetime import date

from ..helpers import _TIMELINE_EXCLUDED_DATA_TYPES


class _TimelineAddress:
    """Address row shaped like organization data so the timeline can mix both."""

    def __init__(self, address):
        self.valid_from = address.valid_from
        self.valid_to = address.valid_to
        self.data_type = "headquarters" if address.is_headquarters else "address"
        self.value = str(address.address or "")
        self.data_reference = ""
        self._source_label = address.source_label()

    def source_label(self):
        return self._source_label


def timeline_entries(organization):
    data = (
        organization.to_organizationatlasdata.select_related("data_type")
        .with_data_reference()
        .exclude(data_type__data_type__in=_TIMELINE_EXCLUDED_DATA_TYPES)
    )
    entries = list(data)
    for address in organization.to_organizationatlasaddress.all():
        if not str(address.address or "").strip():
            continue
        entries.append(_TimelineAddress(address))
    entries.sort(
        key=lambda row: (
            row.valid_from is None,
            row.valid_from or date.min,
            str(row.data_type),
        )
    )
    return entries


def timeline_groups(rows):
    groups = []
    current_start = object()
    current = None
    for row in rows:
        if row.valid_from != current_start:
            current_start = row.valid_from
            current = {"valid_from": row.valid_from, "rows": []}
            groups.append(current)
        current["rows"].append(row)
    return groups
