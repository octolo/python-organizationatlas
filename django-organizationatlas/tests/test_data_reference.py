import pytest
from django.core.exceptions import ValidationError

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


@pytest.mark.django_db
def test_data_uses_its_type_category_for_reference_lookup():
    organization = OrganizationAtlasOrganization.objects.create(
        denomination='Octolo', code='1', source='test', country_code='FR',
    )
    data = []
    for country, display, description in (
        ('FR', 'ab.cd', 'French meaning'),
        ('BE', 'a.bc.d', 'Belgian meaning'),
    ):
        category = OrganizationAtlasReferenceCategory.objects.create(
            name='Activity', country_code=country,
        )
        reference = OrganizationAtlasReference.objects.create(
            category=category, code=display, description=description,
            source='test', country_code=country,
        )
        datatype = OrganizationAtlasDataType.for_key('activity', category=category)
        row = OrganizationAtlasData.objects.create(
            organization=organization, data_type=datatype,
            country_code=country, source='test', value='ABCD',
        )
        data.append((row, reference, description))

    for row, reference, description in data:
        assert row.value == reference.display_code
        assert row.data_reference == description
        assert OrganizationAtlasData.objects.with_data_reference().get(
            pk=row.pk,
        ).data_reference == description
        assert OrganizationAtlasReference.objects.with_usage_count().get(
            pk=reference.pk,
        ).sql_used_count == 1


@pytest.mark.django_db
def test_used_count_counts_data_values_matching_the_code():
    organization = OrganizationAtlasOrganization.objects.create(
        denomination="Octolo",
        code="917432254",
        source="INSEE",
        country_code="FR",
    )
    category = OrganizationAtlasReferenceCategory.for_name("ape", "FR")
    used = OrganizationAtlasReference.objects.create(
        category=category,
        code="62.01Z",
        description="Programmation informatique",
        country_code="FR",
        source="insee",
    )
    unused = OrganizationAtlasReference.objects.create(
        category=category,
        code="01.11Z",
        description="Culture de céréales",
        country_code="FR",
        source="insee",
    )
    OrganizationAtlasData.objects.create(
        organization=organization,
        source="INSEE",
        country_code="FR",
        data_type=OrganizationAtlasDataType.for_key("ape"),
        value="62.01Z",
    )

    counts = {
        reference.code: reference.sql_used_count
        for reference in OrganizationAtlasReference.objects.with_usage_count()
    }

    assert counts[used.code] == 1
    assert counts[unused.code] == 0


@pytest.mark.django_db
def test_reference_code_and_data_value_use_distinct_forms():
    organization = OrganizationAtlasOrganization.objects.create(
        denomination='Octolo',
        code='917432254',
        source='INSEE',
        country_code='FR',
    )
    category = OrganizationAtlasReferenceCategory.for_name('ape', 'FR')
    reference = OrganizationAtlasReference.objects.create(
        category=category,
        code='62.01z',
        description='Programmation informatique',
        country_code='FR',
        source='insee',
    )
    assert reference.code == '6201Z'
    assert reference.display_code == '62.01z'
    for source, value in [('insee', '62.01z'), ('inpi', '6201Z')]:
        data = OrganizationAtlasData.objects.create(
            organization=organization,
            source=source,
            country_code='FR',
            data_type=OrganizationAtlasDataType.for_key('ape'),
            value=value,
        )
        assert data.value == '62.01z'
        assert data.data_reference == 'Programmation informatique'
        annotated = OrganizationAtlasData.objects.with_data_reference().get(pk=data.pk)
        assert annotated.data_reference == data.data_reference
    assert (
        OrganizationAtlasReference.objects.with_usage_count()
        .get(pk=reference.pk).sql_used_count == 2
    )


@pytest.mark.django_db
def test_reference_lookup_respects_country_and_preserves_unknown_values():
    organization = OrganizationAtlasOrganization.objects.create(
        denomination='Octolo', code='1', source='insee', country_code='FR',
    )
    OrganizationAtlasReference.objects.create(
        category=OrganizationAtlasReferenceCategory.for_name('ape', 'BE'),
        code='ab.cd', description='Belgium', country_code='BE', source='test',
    )
    data = OrganizationAtlasData.objects.create(
        organization=organization,
        source='insee',
        country_code='FR',
        data_type=OrganizationAtlasDataType.for_key('ape'),
        value='ABCD',
    )
    assert data.value == 'ABCD'
    assert data.data_reference == ''
    assert OrganizationAtlasData.objects.with_data_reference().get(
        pk=data.pk,
    ).data_reference == ''


@pytest.mark.django_db
def test_reference_does_not_change_non_string_typed_values():
    organization = OrganizationAtlasOrganization.objects.create(
        denomination='Octolo', code='1', source='test', country_code='FR',
    )
    OrganizationAtlasReference.objects.create(
        category=OrganizationAtlasReferenceCategory.for_name('employees', 'FR'),
        code='1.0', source='test', country_code='FR',
    )
    data = OrganizationAtlasData.objects.create(
        organization=organization, source='test', country_code='FR',
        data_type=OrganizationAtlasDataType.for_key('employees', 'int'),
        value='10',
    )
    assert data.value == '10'
    assert data.typed_value == 10


@pytest.mark.django_db
def test_specific_reference_takes_precedence_over_global_reference():
    organization = OrganizationAtlasOrganization.objects.create(
        denomination='Octolo', code='1', source='insee', country_code='FR',
    )
    global_reference = OrganizationAtlasReference.objects.create(
        category=OrganizationAtlasReferenceCategory.for_name('ape', ''),
        code='ab.cd', description='Global', source='test',
    )
    french_reference = OrganizationAtlasReference.objects.create(
        category=OrganizationAtlasReferenceCategory.for_name('ape', 'FR'),
        code='ab.cd', description='French', source='test',
    )
    data = OrganizationAtlasData.objects.create(
        organization=organization, source='user', country_code='XX',
        data_type=OrganizationAtlasDataType.for_key('ape'), value='ABCD',
    )
    belgian = OrganizationAtlasOrganization.objects.create(
        denomination='Other', code='2', source='test', country_code='BE',
    )
    global_data = OrganizationAtlasData.objects.create(
        organization=belgian, source='test', country_code='BE',
        data_type=OrganizationAtlasDataType.for_key('ape'), value='ABCD',
    )

    assert data.value == 'ab.cd'
    assert data.data_reference == 'French'
    assert OrganizationAtlasData.objects.with_data_reference().get(
        pk=data.pk,
    ).data_reference == 'French'
    assert global_data.data_reference == 'Global'
    counts = {
        row.pk: row.sql_used_count
        for row in OrganizationAtlasReference.objects.with_usage_count()
    }
    assert counts[french_reference.pk] == 1
    assert counts[global_reference.pk] == 1


@pytest.mark.django_db
def test_used_reference_display_code_cannot_be_changed():
    organization = OrganizationAtlasOrganization.objects.create(
        denomination='Octolo', code='1', source='insee', country_code='FR',
    )
    reference = OrganizationAtlasReference.objects.create(
        category=OrganizationAtlasReferenceCategory.for_name('ape', 'FR'),
        code='62.01Z', source='insee', country_code='FR',
    )
    OrganizationAtlasData.objects.create(
        organization=organization,
        source='insee',
        country_code='FR',
        data_type=OrganizationAtlasDataType.for_key('ape'),
        value='6201Z',
    )
    reference.display_code = '6201Z'
    with pytest.raises(ValidationError):
        reference.save()
