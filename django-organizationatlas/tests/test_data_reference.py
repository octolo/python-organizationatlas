import pytest

from django_organizationatlas.models import (
    OrganizationAtlasData,
    OrganizationAtlasDataType,
    OrganizationAtlasOrganization,
    OrganizationAtlasReference,
    OrganizationAtlasReferenceCategory,
)


@pytest.mark.django_db
def test_data_reference_resolves_description_from_code():
    organization = OrganizationAtlasOrganization.objects.create(
        denomination="Octolo",
        code="917432254",
        source="INSEE",
        country_code="FR",
    )
    category = OrganizationAtlasReferenceCategory.for_name("ape", "FR")
    OrganizationAtlasReference.objects.create(
        category=category,
        code="6201Z",
        description="Programmation informatique",
        country_code="FR",
        source="insee",
    )
    data = OrganizationAtlasData.objects.create(
        organization=organization,
        source="INSEE",
        country_code="FR",
        data_type=OrganizationAtlasDataType.for_key("ape"),
        value="6201Z",
    )

    annotated = OrganizationAtlasData.objects.with_data_reference().get(pk=data.pk)

    assert annotated.data_reference == "Programmation informatique"
