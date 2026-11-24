import subprocess
import sys
from datetime import date, timedelta

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.files.storage.handler import InvalidStorageError
from django.utils import timezone

from django_organizationatlas.models import (
    OrganizationAtlasData,
    OrganizationAtlasDataType,
    OrganizationAtlasOrganization,
    OrganizationAtlasReferenceCategory,
)


@pytest.fixture
def organization(db):
    return OrganizationAtlasOrganization.objects.create(
        denomination="Octolo",
        code="917432254",
        source="insee",
        country_code="FR",
    )


@pytest.mark.parametrize(
    ("value_type", "value", "expected"),
    [
        ("str", "text", "text"),
        ("int", "42", 42),
        ("float", "4.2", 4.2),
        ("bool", "yes", True),
        ("bool", "off", False),
        ("date", "2026-10-29", date(2026, 10, 29)),
        ("json", '{"active": true}', {"active": True}),
    ],
)
@pytest.mark.django_db
def test_typed_value(organization, value_type, value, expected):
    data = OrganizationAtlasData(
        organization=organization,
        data_type=OrganizationAtlasDataType.objects.create(
            data_type=f"{value_type}-{value}",
            value_type=value_type,
        ),
        value=value,
    )

    assert data.typed_value == expected


@pytest.mark.parametrize(
    ("value_type", "value"),
    [
        ("int", "four"),
        ("float", "four"),
        ("bool", "perhaps"),
        ("date", "29/10/2026"),
        ("json", "{invalid"),
    ],
)
@pytest.mark.django_db
def test_clean_rejects_value_that_does_not_match_type(
    organization,
    value_type,
    value,
):
    data = OrganizationAtlasData(
        organization=organization,
        data_type=OrganizationAtlasDataType.objects.create(
            data_type=f"invalid-{value_type}",
            value_type=value_type,
        ),
        value=value,
    )

    with pytest.raises(ValidationError) as exc:
        data.clean()

    assert "value" in exc.value.message_dict


@pytest.mark.django_db
def test_data_type_rejects_conflicting_value_type():
    OrganizationAtlasDataType.for_key("employees", "int")

    with pytest.raises(ValueError, match="already uses value type"):
        OrganizationAtlasDataType.for_key("employees", "str")


@pytest.mark.django_db
def test_data_type_key_is_scoped_to_its_optional_category():
    france = OrganizationAtlasReferenceCategory.for_name('Activity', 'FR')
    belgium = OrganizationAtlasReferenceCategory.for_name('Activity', 'BE')

    french_type = OrganizationAtlasDataType.for_key('activity', category=france)
    belgian_type = OrganizationAtlasDataType.for_key(
        'activity', 'int', category=belgium,
    )
    uncategorized = OrganizationAtlasDataType.for_key('activity')

    assert len({french_type.pk, belgian_type.pk, uncategorized.pk}) == 3
    assert OrganizationAtlasDataType.for_key(
        'activity', category=france,
    ) == french_type
    assert OrganizationAtlasDataType.objects.for_provider(
        'Activity', 'int', 'BE',
    ).category == belgium


@pytest.mark.django_db
def test_provider_category_is_not_blocked_by_uncategorized_data_in_other_country(
    organization,
):
    uncategorized = OrganizationAtlasDataType.for_key('activity')
    OrganizationAtlasData.objects.create(
        organization=organization, data_type=uncategorized,
        country_code='FR', source='provider', value='value',
    )
    belgium = OrganizationAtlasReferenceCategory.for_name('activity', 'BE')

    datatype = OrganizationAtlasDataType.objects.for_provider(
        'activity', 'str', 'BE',
    )

    assert datatype.category == belgium
    assert OrganizationAtlasDataType.objects.for_provider(
        'activity', 'str', 'FR',
    ) == uncategorized


@pytest.mark.django_db
def test_unique_category_closes_existing_active_data(organization):
    today = timezone.localdate()
    category = OrganizationAtlasReferenceCategory.objects.create(
        name='Unique', country_code='', unique=True,
    )
    datatype = OrganizationAtlasDataType.for_key('unique', category=category)
    previous = OrganizationAtlasData.objects.create(
        organization=organization, data_type=datatype, value='old',
        source='first', valid_to=today + timedelta(days=1),
    )

    current = OrganizationAtlasData.objects.create(
        organization=organization, data_type=datatype, value='new',
        source='second', country_code='FR',
    )

    previous.refresh_from_db()
    assert previous.valid_to == today
    assert previous.history.first().valid_to == today
    assert not previous.is_current
    assert current.is_current


@pytest.mark.django_db
def test_unique_category_cannot_close_a_future_period(organization):
    today = timezone.localdate()
    category = OrganizationAtlasReferenceCategory.objects.create(
        name='Unique', country_code='', unique=True,
    )
    datatype = OrganizationAtlasDataType.for_key('unique', category=category)
    previous = OrganizationAtlasData.objects.create(
        organization=organization, data_type=datatype, value='future',
        valid_from=today + timedelta(days=1),
    )

    with pytest.raises(ValidationError, match='before its start date'):
        OrganizationAtlasData.objects.create(
            organization=organization, data_type=datatype, value='new',
        )

    previous.refresh_from_db()
    assert previous.valid_to is None


@pytest.mark.django_db
def test_non_unique_category_replaces_only_active_main(organization):
    today = timezone.localdate()
    category = OrganizationAtlasReferenceCategory.objects.create(
        name='Multiple', country_code='', unique=False,
    )
    datatype = OrganizationAtlasDataType.for_key('multiple', category=category)
    old = OrganizationAtlasData.objects.create(
        organization=organization, data_type=datatype, value='old',
        source='same', main=True, valid_to=today,
    )
    previous = OrganizationAtlasData.objects.create(
        organization=organization, data_type=datatype, value='first',
        source='same', main=True, valid_to=today + timedelta(days=1),
    )
    current = OrganizationAtlasData.objects.create(
        organization=organization, data_type=datatype, value='second',
        source='same', main=True,
    )

    old.refresh_from_db()
    previous.refresh_from_db()
    assert old.main is True
    assert previous.main is False
    assert previous.history.first().main is False
    assert current.main is True
    assert previous.is_current and current.is_current


@pytest.mark.django_db
def test_category_cannot_become_unique_with_active_duplicates(organization):
    category = OrganizationAtlasReferenceCategory.objects.create(
        name='Multiple', country_code='', unique=False,
    )
    datatype = OrganizationAtlasDataType.for_key('multiple', category=category)
    for value in ('first', 'second'):
        OrganizationAtlasData.objects.create(
            organization=organization, data_type=datatype, value=value,
        )
    category.unique = True

    with pytest.raises(ValidationError, match='Resolve active data duplicates'):
        category.save(update_fields=['unique'])

    category.refresh_from_db()
    assert category.unique is False


@pytest.mark.django_db
def test_assigning_unique_category_rejects_existing_duplicates(organization):
    datatype = OrganizationAtlasDataType.for_key('multiple')
    for source in ('first', 'second'):
        OrganizationAtlasData.objects.create(
            organization=organization, data_type=datatype, value='value',
            source=source,
        )
    datatype.category = OrganizationAtlasReferenceCategory.objects.create(
        name='Unique', country_code='', unique=True,
    )

    with pytest.raises(ValidationError, match='Resolve conflicting active'):
        datatype.save(update_fields=['category'])

    datatype.refresh_from_db()
    assert datatype.category is None


@pytest.mark.django_db
def test_data_main_is_persisted_and_recorded_in_history(organization):
    data = OrganizationAtlasData.objects.create(
        organization=organization,
        data_type=OrganizationAtlasDataType.for_key('name'),
        value='Example',
    )
    assert data.main is False
    assert data.history.first().main is False

    data.main = True
    data.save(update_fields=['main'])
    data.refresh_from_db()

    assert data.main is True
    assert data.history.first().main is True


@pytest.mark.parametrize('value_type', ['image', 'file'])
@pytest.mark.django_db
def test_file_types_require_a_file_and_no_text(organization, value_type):
    data = OrganizationAtlasData(
        organization=organization,
        data_type=OrganizationAtlasDataType.for_key(value_type, value_type),
        value='',
    )
    with pytest.raises(ValidationError) as error:
        data.clean()
    assert 'file' in error.value.message_dict

    data.file = SimpleUploadedFile('test.bin', b'not an image')
    data.value = 'text'
    with pytest.raises(ValidationError) as error:
        data.clean()
    assert 'value' in error.value.message_dict


@pytest.mark.django_db
def test_image_type_rejects_invalid_image(organization):
    data = OrganizationAtlasData(
        organization=organization,
        data_type=OrganizationAtlasDataType.for_key('logo', 'image'),
        file=SimpleUploadedFile('logo.png', b'not an image'),
    )
    with pytest.raises(ValidationError) as error:
        data.clean()
    assert 'file' in error.value.message_dict


@pytest.mark.parametrize('configured', [False, True])
def test_data_file_storage_and_path_at_startup(tmp_path, configured):
    script = '''
import sys
from pathlib import Path
from unittest.mock import patch
from datetime import datetime

import django
from django.conf import settings
from django.core.files.base import ContentFile

root = Path(sys.argv[1])
configured = sys.argv[2] == 'True'
settings.MEDIA_ROOT = root / 'default'
if configured:
    settings.STORAGES = {
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'organization_data': {
            'BACKEND': 'django.core.files.storage.FileSystemStorage',
            'OPTIONS': {'location': root / 'custom'},
        },
    }
    settings.ORGANIZATIONATLAS_DATA_FILE_STORAGE = 'organization_data'
    settings.ORGANIZATIONATLAS_DATA_FILE_UPLOAD_TO = 'custom/%Y/%m/'
django.setup()

from django_organizationatlas.models import OrganizationAtlasData

data = OrganizationAtlasData()
with patch('django_organizationatlas.storage.datetime') as clock:
    clock.now.return_value = datetime(2026, 1, 2)
    data.file.save('logo.txt', ContentFile(b'logo'), save=False)
prefix = 'custom' if configured else 'organizationatlas/data'
assert data.file.name == prefix + '/2026/01/logo.txt'
storage_root = root / ('custom' if configured else 'default')
assert (storage_root / data.file.name).read_bytes() == b'logo'
'''
    subprocess.run(
        [sys.executable, '-c', script, str(tmp_path), str(configured)],
        check=True,
        capture_output=True,
        text=True,
    )


def test_data_file_upload_to_supports_callable(settings):
    settings.ORGANIZATIONATLAS_DATA_FILE_UPLOAD_TO = (
        lambda instance, filename: (
            f'custom/{instance.organization.code}/{filename}'
        )
    )
    instance = OrganizationAtlasData(
        organization=OrganizationAtlasOrganization(code='123'),
    )
    field = OrganizationAtlasData._meta.get_field('file')

    assert field.generate_filename(instance, 'logo.png') == 'custom/123/logo.png'


def test_data_file_storage_rejects_unknown_alias(settings):
    from django_organizationatlas.storage import data_file_storage

    settings.ORGANIZATIONATLAS_DATA_FILE_STORAGE = 'missing'

    with pytest.raises(InvalidStorageError, match='missing'):
        data_file_storage()
