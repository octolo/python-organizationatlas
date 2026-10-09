from datetime import date

from django.db import transaction

from django_organizationatlas.models.organization import OrganizationAtlasOrganization
from django_organizationatlas.models.data import OrganizationAtlasData, OrganizationAtlasDataType


@transaction.atomic
def create_source(
    backend: str,
    organization: OrganizationAtlasOrganization,
    data_type: str,
    value_type: str,
    value: str,
    country_code: str = "",
    metadata: dict | None = None,
    valid_from: date | None = None,
) -> OrganizationAtlasData:
    """Record a value for a (organization, source, country, data_type) key.

    Versioning: if an open record (valid_to IS NULL) already exists with a
    different value, it is closed (valid_to = valid_from or today) and a new
    open record is inserted. If the value is unchanged, the existing record is
    returned untouched.
    """
    effective_date = valid_from or date.today()
    datatype = OrganizationAtlasDataType.for_key(data_type, value_type)

    open_record = OrganizationAtlasData.objects.filter(
        organization=organization,
        source=backend,
        country_code=country_code,
        data_type=datatype,
        valid_to__isnull=True,
    ).first()

    if open_record is not None:
        if open_record.value == value:
            return open_record
        open_record.valid_to = effective_date
        open_record.save(update_fields=["valid_to", "updated_at"])

    return OrganizationAtlasData.objects.create(
        organization=organization,
        source=backend,
        country_code=country_code,
        data_type=datatype,
        value=value,
        metadata=metadata or {},
        valid_from=effective_date,
    )
