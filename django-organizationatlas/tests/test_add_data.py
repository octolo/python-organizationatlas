import re
from datetime import date, datetime, timezone as datetime_timezone
from io import BytesIO
from unittest.mock import patch

import pytest
from PIL import Image
from django.contrib.auth.models import Permission
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from django_organizationatlas.models import (
    OrganizationAtlasAddress,
    OrganizationAtlasData,
    OrganizationAtlasDataType,
    OrganizationAtlasOrganization,
    OrganizationAtlasOrganizationRelation,
    OrganizationAtlasReference,
    OrganizationAtlasReferenceCategory,
)
from django_organizationatlas.admin.organization import OrganizationAtlasOrganizationAdmin
from django_organizationatlas.models.source import USER_COUNTRY_CODE
from django_organizationatlas.services.reference import (
    fixtures_root,
    import_csv_file,
)


def _trace_row(organization, code, value):
    category = OrganizationAtlasReferenceCategory.for_name("apitrace", "")
    reference, _created = OrganizationAtlasReference.objects.get_or_create(
        category=category,
        code=code.upper(),
        defaults={"display_code": code, "source": "organizationatlas"},
    )
    row = OrganizationAtlasData.objects.create(
        organization=organization,
        data_type=OrganizationAtlasDataType.for_key("apitrace", "json"),
        value=value,
        source="insee",
        country_code="FR",
        metadata={"trace": code},
    )
    row.reference.add(reference)
    return row


def _organization():
    return OrganizationAtlasOrganization.objects.create(
        denomination="Octolo",
        code="917432254",
        source="INSEE",
        country_code="FR",
    )


def _client():
    user = User.objects.create_superuser("ada", "ada@example.com", "password")
    client = Client()
    client.force_login(user)
    return client, user


def _url(name, organization, query=""):
    url = reverse(
        f"admin:django_organizationatlas_organizationatlasorganization_{name}",
        args=[organization.pk],
    )
    if query:
        return f"{url}?{query}"
    return url


@pytest.mark.django_db
def test_organization_admin_displays_preferred_data_read_only():
    organization = _organization()
    datatype = OrganizationAtlasDataType.for_key('activity')
    for source, value in (
        ('first', '<preferred>'),
        ('second', 'not preferred'),
    ):
        OrganizationAtlasData.objects.create(
            organization=organization, data_type=datatype,
            source=source, country_code='FR', value=value,
        )
    OrganizationAtlasData.objects.create(
        organization=organization, data_type=datatype,
        source='first', country_code='BE', value='Belgian value',
    )
    OrganizationAtlasData.objects.create(
        organization=organization, data_type=datatype,
        source='old', country_code='FR', value='expired value',
        valid_to=timezone.localdate(),
    )
    OrganizationAtlasData.objects.create(
        organization=organization,
        data_type=OrganizationAtlasDataType.for_key('logo', 'file'),
        source='first', country_code='BE', file='logos/logo.png',
    )
    client, _user = _client()

    with patch(
        'django_organizationatlas.services.refresh._priorities',
        return_value={'first': 10, 'second': 1},
    ):
        response = client.get(_url('change', organization))

    assert response.status_code == 200
    adminform = response.context['adminform']
    assert 'preferred_data_display' in adminform.fieldsets[0][1]['fields']
    assert 'preferred_data_display' not in adminform.form.fields
    preferred = next(
        field
        for fieldset in adminform
        for line in fieldset
        for field in line
        if field.is_readonly
        and field.field['name'] == 'preferred_data_display'
    )
    with patch(
        'django_organizationatlas.services.refresh._priorities',
        return_value={'first': 10, 'second': 1},
    ):
        content = str(preferred.contents())
    assert 'FR / activity' in content
    assert '&lt;preferred&gt;' in content
    assert 'not preferred' not in content
    assert 'expired value' not in content
    assert 'BE / activity' in content
    assert 'Belgian value' in content
    assert 'logos/logo.png' in content


@pytest.mark.django_db
def test_organization_admin_hides_preferred_data_without_data_permission():
    organization = _organization()
    user = User.objects.create_user(
        username='viewer', password='password', is_staff=True,
    )
    user.user_permissions.add(
        Permission.objects.get(
            codename='view_organizationatlasorganization',
            content_type__app_label='django_organizationatlas',
        ),
    )
    client = Client()
    client.force_login(user)

    response = client.get(_url('change', organization))

    assert response.status_code == 200
    assert 'preferred_data_display' not in (
        response.context['adminform'].fieldsets[0][1]['fields']
    )


@pytest.mark.django_db
def test_data_inline_value_has_one_row():
    organization = _organization()
    OrganizationAtlasData.objects.create(
        organization=organization,
        data_type=OrganizationAtlasDataType.for_key('inline_value'),
        value='first\nsecond',
        source='test',
    )
    client, _user = _client()

    response = client.get(_url('change', organization))

    assert response.status_code == 200
    textarea = re.search(
        r'<textarea\b(?=[^>]*name="to_organizationatlasdata-0-value")'
        r'(?=[^>]*rows="1")[^>]*>(.*?)</textarea>',
        response.content.decode(),
        re.DOTALL,
    )
    assert textarea is not None
    assert 'first\nsecond' in textarea.group(1)


@pytest.mark.django_db
def test_visual_identity_upload_and_text_in_admin(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    settings.MEDIA_URL = '/media/'
    organization = _organization()
    client, _user = _client()
    font = OrganizationAtlasReference.objects.get(
        category__name='Visual identity', code='FONT',
    )
    color = OrganizationAtlasReference.objects.get(
        category__name='Visual identity', code='PRIMARY_COLOR',
    )
    font_url = _url('add_reference_data', organization, f'reference={font.pk}')
    color_url = _url('add_reference_data', organization, f'reference={color.pk}')

    page = client.get(font_url)
    assert 'multipart/form-data' in page.content.decode()
    assert 'name="file"' in page.content.decode()
    response = client.post(
        font_url,
        {'file': SimpleUploadedFile('font.woff2', b'font data')},
    )
    assert response.status_code == 302
    row = organization.to_organizationatlasdata.get(
        data_type__data_type='visual_identity_font',
    )
    assert row.data_type.value_type == 'file'
    assert font.category.unique is False
    assert row.value == ''
    assert row.file.read() == b'font data'
    assert row.reference.get() == font
    assert row.history.first().file == row.file.name
    change = client.get(_url('change', organization)).content.decode()
    assert row.file.url in change
    data_list = client.get(_url('list_data', organization), follow=True)
    assert row.file.url in data_list.content.decode()

    response = client.post(color_url, {'value': '#123456'})
    assert response.status_code == 302
    color_row = organization.to_organizationatlasdata.get(
        data_type__data_type='visual_identity_primary_color',
    )
    assert color_row.value == '#123456'
    assert color.category.unique is False

    timeline = client.get(_url('timeline', organization)).content.decode()
    assert row.file.url in timeline
    assert '#123456' in timeline


@pytest.mark.django_db
def test_visual_identity_image_requires_valid_upload(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    organization = _organization()
    client, _user = _client()
    logo = OrganizationAtlasReference.objects.get(
        category__name='Visual identity', code='LOGO',
    )
    url = _url('add_reference_data', organization, f'reference={logo.pk}')
    response = client.post(
        url,
        {'file': SimpleUploadedFile('logo.png', b'not an image')},
    )
    assert response.status_code == 200
    assert not organization.to_organizationatlasdata.exists()
    assert 'Upload a valid image' in response.content.decode()

    content = BytesIO()
    Image.new('RGB', (1, 1)).save(content, format='PNG')
    response = client.post(
        url,
        {'file': SimpleUploadedFile('logo.png', content.getvalue())},
    )
    assert response.status_code == 302
    row = organization.to_organizationatlasdata.get()
    assert row.data_type.value_type == 'image'
    row.clean()
    assert row.typed_value == row.file


@pytest.mark.django_db
def test_reference_uses_existing_custom_file_type(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    organization = _organization()
    client, _user = _client()
    data_type = OrganizationAtlasDataType.for_key('attachment', 'file')
    category = OrganizationAtlasReferenceCategory.for_name('attachment', '')
    reference = OrganizationAtlasReference.objects.create(
        category=category, code='DOCUMENT', source='test',
    )
    url = _url('add_reference_data', organization, f'reference={reference.pk}')

    page = client.get(url)
    assert 'multipart/form-data' in page.content.decode()
    response = client.post(
        url,
        {'file': SimpleUploadedFile('document.pdf', b'example')},
    )
    assert response.status_code == 302
    row = organization.to_organizationatlasdata.get()
    assert row.data_type == data_type
    assert row.file.read() == b'example'


@pytest.mark.django_db
def test_list_data_opens_data_admin_for_the_organization():
    organization = _organization()
    other = OrganizationAtlasOrganization.objects.create(
        denomination="Other",
        code="111111111",
        source="insee",
        country_code="FR",
    )
    OrganizationAtlasData.objects.create(
        organization=organization,
        data_type=OrganizationAtlasDataType.for_key("denomination"),
        value="kept-value",
        source="insee",
        country_code="FR",
    )
    OrganizationAtlasData.objects.create(
        organization=other,
        data_type=OrganizationAtlasDataType.for_key("denomination"),
        value="hidden-value",
        source="insee",
        country_code="FR",
    )
    client, _user = _client()

    change = client.get(_url("change", organization))
    assert f'{_url("list_data", organization)}">Data</a>' in change.content.decode()

    response = client.get(_url("list_data", organization))
    assert response.status_code == 302
    assert response.url.endswith(f"?organization_id={organization.pk}")

    page = client.get(response.url)
    html = page.content.decode()
    assert page.status_code == 200
    assert "kept-value" in html
    assert "hidden-value" not in html


@pytest.mark.django_db
def test_data_inline_hides_traces_and_links_to_filtered_lists():
    organization = _organization()
    OrganizationAtlasData.objects.create(
        organization=organization,
        data_type=OrganizationAtlasDataType.for_key("denomination"),
        value="visible-name",
        source="insee",
        country_code="FR",
    )
    _trace_row(organization, "source", "secret-api-trace")
    _trace_row(organization, "history", "secret-history-trace")
    client, _user = _client()

    change = client.get(_url("change", organization))
    change_html = change.content.decode()
    assert "visible-name" in change_html
    assert "secret-api-trace" not in change_html
    assert "secret-history-trace" not in change_html
    assert f'{_url("list_data", organization)}">Data</a>' in change_html
    assert "API trace" not in change_html
    assert "API history" not in change_html


@pytest.mark.django_db
def test_data_inline_shows_current_rows_and_counts_older_ones():
    organization = _organization()
    denomination = OrganizationAtlasDataType.for_key("denomination")
    ape = OrganizationAtlasDataType.for_key("ape")
    OrganizationAtlasData.objects.create(
        organization=organization,
        data_type=denomination,
        value="former-name",
        valid_from=date(2010, 1, 1),
        valid_to=date(2019, 12, 31),
        source="insee",
        country_code="FR",
    )
    current_name = OrganizationAtlasData.objects.create(
        organization=organization,
        data_type=denomination,
        value="current-name",
        valid_from=date(2020, 1, 1),
        source="insee",
        country_code="FR",
    )
    current_ape_a = OrganizationAtlasData.objects.create(
        organization=organization,
        data_type=ape,
        value="current-ape-a",
        source="insee",
        country_code="FR",
    )
    current_ape_b = OrganizationAtlasData.objects.create(
        organization=organization,
        data_type=ape,
        value="current-ape-b",
        source="other",
        country_code="FR",
    )
    client, _user = _client()

    html = client.get(_url("change", organization)).content.decode()

    assert "current-name" in html
    assert "current-ape-a" in html
    assert "current-ape-b" in html
    assert "former-name" not in html
    for row in (current_name, current_ape_a, current_ape_b):
        change_url = reverse(
            "admin:django_organizationatlas_organizationatlasdata_change",
            args=[row.pk],
        )
        assert change_url in html
    older_counts = re.findall(r'class="field-older_count">\s*<p>(\d+)</p>', html)
    assert sorted(older_counts) == ["0", "0", "1"]


@pytest.mark.django_db
def test_list_address_and_relations_filter_by_organization():
    organization = _organization()
    other = OrganizationAtlasOrganization.objects.create(
        denomination="Other",
        code="111111111",
        source="INSEE",
        country_code="FR",
    )
    target = OrganizationAtlasOrganization.objects.create(
        denomination="Target Co",
        code="222222222",
        source="INSEE",
        country_code="FR",
    )
    hidden_target = OrganizationAtlasOrganization.objects.create(
        denomination="Hidden Co",
        code="333333333",
        source="INSEE",
        country_code="FR",
    )
    OrganizationAtlasAddress.objects.create(
        organization=organization,
        source="insee",
        country_code="FR",
        address={"address_line1": "1 rue Kept"},
    )
    OrganizationAtlasAddress.objects.create(
        organization=other,
        source="insee",
        country_code="FR",
        address={"address_line1": "9 rue Hidden"},
    )
    OrganizationAtlasOrganizationRelation.objects.create(
        from_organization=organization,
        to_organization=target,
        source="insee",
        country_code="FR",
    )
    OrganizationAtlasOrganizationRelation.objects.create(
        from_organization=other,
        to_organization=hidden_target,
        source="insee",
        country_code="FR",
    )
    client, _user = _client()
    change = client.get(_url("change", organization))
    html = change.content.decode()
    assert f'{_url("list_address", organization)}">Address</a>' in html
    assert f'{_url("list_relations", organization)}">Relations</a>' in html

    address = client.get(_url("list_address", organization), follow=True)
    address_html = address.content.decode()
    assert "1 rue Kept" in address_html
    assert "9 rue Hidden" not in address_html

    relations = client.get(_url("list_relations", organization), follow=True)
    relations_html = relations.content.decode()
    assert "Target Co" in relations_html
    assert "Hidden Co" not in relations_html


@pytest.mark.django_db
def test_timeline_groups_data_by_date_and_skips_apitrace():
    organization = _organization()
    other = OrganizationAtlasOrganization.objects.create(
        denomination="Other",
        code="111111111",
        source="INSEE",
        country_code="FR",
    )
    OrganizationAtlasData.objects.create(
        organization=organization,
        data_type=OrganizationAtlasDataType.for_key("denomination"),
        value="OLD",
        valid_from=date(2010, 1, 1),
        valid_to=date(2019, 12, 31),
        source="insee",
        country_code="FR",
    )
    OrganizationAtlasData.objects.create(
        organization=organization,
        data_type=OrganizationAtlasDataType.for_key("denomination"),
        value="NEW",
        valid_from=date(2020, 1, 1),
        source="insee",
        country_code="FR",
    )
    OrganizationAtlasData.objects.create(
        organization=organization,
        data_type=OrganizationAtlasDataType.for_key("apitrace"),
        value="secret-trace",
        valid_from=date(2020, 1, 1),
        source="insee",
        country_code="FR",
    )
    OrganizationAtlasData.objects.create(
        organization=organization,
        data_type=OrganizationAtlasDataType.for_key("apihistorytrace", "json"),
        value="history-secret",
        valid_from=date(2020, 1, 1),
        source="insee",
        country_code="FR",
    )
    OrganizationAtlasAddress.objects.create(
        organization=organization,
        source="insee",
        country_code="FR",
        address={"address_line1": "1 rue Kept", "city": "Paris"},
        is_headquarters=True,
    )
    OrganizationAtlasData.objects.create(
        organization=other,
        data_type=OrganizationAtlasDataType.for_key("denomination"),
        value="OTHER",
        valid_from=date(2010, 1, 1),
        source="insee",
        country_code="FR",
    )
    client, _user = _client()

    change = client.get(_url("change", organization))
    assert "Timeline" in change.content.decode()

    page = client.get(_url("timeline", organization))
    assert page.status_code == 200
    html = page.content.decode()
    assert html.index("2010-01-01") < html.index("2020-01-01")
    assert "OLD" in html
    assert "NEW" in html
    assert "secret-trace" not in html
    assert "history-secret" not in html
    assert "OTHER" not in html
    assert "1 rue Kept" in html
    assert "headquarters" in html
    assert timezone.localdate().isoformat() in html
    assert 'Recorded' in html


@pytest.mark.django_db
def test_start_at_uses_recorded_date_then_real_validity_date():
    organization = _organization()
    data = OrganizationAtlasData.objects.create(
        organization=organization,
        data_type=OrganizationAtlasDataType.for_key('ape'),
        value='6201Z',
        source='insee',
        country_code='FR',
    )
    OrganizationAtlasData.objects.filter(pk=data.pk).update(
        created_at=datetime(2024, 3, 4, 23, 30, tzinfo=datetime_timezone.utc),
    )
    other = OrganizationAtlasData.objects.create(
        organization=organization,
        data_type=OrganizationAtlasDataType.for_key('denomination'),
        value='Name',
        source='insee',
        country_code='FR',
        valid_from=date(2021, 1, 1),
    )
    with timezone.override('Pacific/Kiritimati'):
        rows = organization.to_organizationatlasdata.with_start_at()
        row = rows.get(pk=data.pk)
        assert row.start_at == date(2024, 3, 5)
        assert row.valid_from is None
        assert list(rows.order_by('start_at').values_list('pk', flat=True)) == [
            other.pk, data.pk,
        ]

        OrganizationAtlasData.objects.filter(pk=data.pk).update(
            valid_from=date(2020, 1, 1),
        )
        row = rows.get(pk=data.pk)
        assert row.start_at == date(2020, 1, 1)
        assert list(rows.order_by('start_at').values_list('pk', flat=True)) == [
            data.pk, other.pk,
        ]


@pytest.mark.django_db
def test_data_start_date_moves_in_timeline_after_valid_from_is_supplied():
    organization = _organization()
    data = OrganizationAtlasData.objects.create(
        organization=organization,
        data_type=OrganizationAtlasDataType.for_key('ape'),
        value='6201Z',
        source='insee',
        country_code='FR',
    )
    OrganizationAtlasData.objects.filter(pk=data.pk).update(
        created_at=datetime(2024, 3, 4, tzinfo=datetime_timezone.utc),
    )
    client, _user = _client()
    html = client.get(_url('timeline', organization)).content.decode()
    assert '2024-03-04' in html
    assert 'Recorded' in html

    OrganizationAtlasData.objects.filter(pk=data.pk).update(
        valid_from=date(2020, 1, 1),
    )
    html = client.get(_url('timeline', organization)).content.decode()
    assert '2020-01-01' in html
    assert '2024-03-04' not in html
    assert 'Recorded' not in html


@pytest.mark.django_db
def test_admin_orders_start_date_and_marks_recorded_dates():
    organization = _organization()
    later = OrganizationAtlasData.objects.create(
        organization=organization,
        data_type=OrganizationAtlasDataType.for_key('ape'),
        value='6201Z',
        source='insee',
        country_code='FR',
    )
    OrganizationAtlasData.objects.filter(pk=later.pk).update(
        created_at=datetime(2024, 3, 4, tzinfo=datetime_timezone.utc),
    )
    earlier = OrganizationAtlasData.objects.create(
        organization=organization,
        data_type=OrganizationAtlasDataType.for_key('denomination'),
        value='Name',
        source='insee',
        country_code='FR',
        valid_from=date(2021, 1, 1),
    )
    client, _user = _client()
    url = reverse(
        'admin:django_organizationatlas_organizationatlasdata_changelist'
    )
    response = client.get(url, {'o': '4'})
    assert response.status_code == 200
    assert [row.pk for row in response.context['cl'].result_list] == [
        earlier.pk, later.pk,
    ]
    assert 'recorded' in response.content.decode()
    descending = client.get(url, {'o': '-4'})
    assert [row.pk for row in descending.context['cl'].result_list] == [
        later.pk, earlier.pk,
    ]
    assert 'recorded' in client.get(
        _url('change', organization)
    ).content.decode()


@pytest.mark.django_db
def test_organization_change_shows_person_inline():
    organization = _organization()
    client, _user = _client()

    html = client.get(_url("change", organization)).content.decode()

    assert "to_organizationatlasperson-group" in html
    assert OrganizationAtlasOrganizationAdmin.inlines
    assert all(inline.show_change_link for inline in OrganizationAtlasOrganizationAdmin.inlines)


@pytest.mark.django_db
def test_timeline_shows_reference_description_when_the_value_matches():
    organization = _organization()
    category = OrganizationAtlasReferenceCategory.for_name("ape", "FR")
    OrganizationAtlasReference.objects.create(
        category=category,
        code="6201Z",
        description="Programmation informatique",
        country_code="FR",
        source="insee",
    )
    OrganizationAtlasData.objects.create(
        organization=organization,
        data_type=OrganizationAtlasDataType.for_key("ape"),
        value="6201Z",
        valid_from=date(2020, 1, 1),
        source="insee",
        country_code="FR",
    )
    OrganizationAtlasData.objects.create(
        organization=organization,
        data_type=OrganizationAtlasDataType.for_key("denomination"),
        value="Octolo",
        valid_from=date(2020, 1, 1),
        source="insee",
        country_code="FR",
    )
    client, _user = _client()

    html = client.get(_url("timeline", organization)).content.decode()
    reference_url = reverse("admin:django_organizationatlas_organizationatlasreference_changelist")
    reference_link = f'{reference_url}?category__id__exact={category.pk}'

    assert "6201Z" in html
    assert "Programmation informatique" in html
    assert html.index("6201Z") < html.index("Programmation informatique")
    assert f'href="{reference_link}">ape</a>' in html
    assert html.count(reference_link) == 1
    assert ">denomination</a>" not in html
    assert ">6201Z</a>" not in html
    assert "Programmation informatique</a>" not in html


@pytest.mark.django_db
def test_organization_detail_opens_reference_list():
    organization = _organization()
    client, _user = _client()

    change = client.get(_url("change", organization))
    content = change.content.decode()
    assert "Actions" in content
    assert "Add data" not in content

    actions = client.get(_url("organization_actions", organization))
    actions_html = actions.content.decode()
    assert actions.status_code == 200
    assert "Add data" in actions_html
    assert _url("add_data_references", organization) in actions_html
    assert _url("refresh", organization) in actions_html
    assert _url("load_history", organization) in actions_html


@pytest.mark.django_db
def test_reference_has_data_type_matches_category_name():
    typed = OrganizationAtlasReferenceCategory.objects.create(name="APE code", country_code="FR")
    untyped = OrganizationAtlasReferenceCategory.objects.create(name="Legal form", country_code="FR")
    OrganizationAtlasDataType.for_key("ape")
    matching = OrganizationAtlasReference.objects.create(
        category=typed,
        code="6201Z",
        description="Programmation",
        source="INSEE",
        country_code="FR",
    )
    OrganizationAtlasReference.objects.create(
        category=untyped,
        code="5710",
        description="SAS",
        source="INSEE",
        country_code="FR",
    )

    found = set(
        OrganizationAtlasReference.objects.with_has_data_type()
        .filter(has_data_type=True)
        .values_list("pk", flat=True)
    )

    assert found == {matching.pk}


@pytest.mark.django_db
def test_add_reference_data_lists_every_reference_and_adds_one():
    organization = _organization()
    client, _user = _client()
    typed = OrganizationAtlasReferenceCategory.objects.create(name="APE code", country_code="FR")
    untyped = OrganizationAtlasReferenceCategory.objects.create(name="Legal form", country_code="FR")
    OrganizationAtlasDataType.for_key("ape")
    OrganizationAtlasReference.objects.create(
        category=typed,
        code="6201Z",
        description="Programmation",
        source="INSEE",
        country_code="FR",
    )
    reference = OrganizationAtlasReference.objects.create(
        category=untyped,
        code="5710",
        description="SAS",
        source="INSEE",
        country_code="FR",
    )

    page = client.get(_url("add_data_references", organization))
    assert page.status_code == 200
    content = page.content.decode()
    assert "Programmation" in content
    assert "SAS" in content
    add_url = _url("add_reference_data", organization, f"reference={reference.pk}")
    assert add_url in content

    response = client.get(add_url)
    assert response.status_code == 200
    assert 'value="5710"' in response.content.decode()
    assert not organization.to_organizationatlasdata.exists()
    assert not OrganizationAtlasDataType.objects.filter(data_type="legalform").exists()

    response = client.post(add_url, {"value": "5710"})
    assert response.status_code == 302
    assert response.url == _url("change", organization)

    row = organization.to_organizationatlasdata.get()
    assert row.data_type.data_type == "legalform"
    assert row.value == "5710"
    assert list(row.reference.all()) == [reference]


@pytest.mark.django_db
def test_add_data_references_uses_reference_admin_filters():
    organization = _organization()
    client, _user = _client()
    france = OrganizationAtlasReferenceCategory.objects.create(name="APE code", country_code="FR")
    belgium = OrganizationAtlasReferenceCategory.objects.create(
        name="Legal form",
        country_code="BE",
    )
    OrganizationAtlasDataType.for_key("ape")
    OrganizationAtlasDataType.for_key("legalform")
    OrganizationAtlasReference.objects.create(
        category=france,
        code="6201Z",
        description="Programmation",
        source="INSEE",
        country_code="FR",
    )
    OrganizationAtlasReference.objects.create(
        category=belgium,
        code="5710",
        description="SAS belge",
        source="INSEE",
        country_code="BE",
    )

    page = client.get(_url("add_data_references", organization))
    content = page.content.decode()
    assert page.status_code == 200
    assert 'id="changelist-filter"' in content
    assert "Programmation" in content
    assert "SAS belge" in content
    assert "category__country_code=FR" in content
    assert f"category__id__exact={belgium.pk}" in content

    by_country = client.get(
        _url("add_data_references", organization, "category__country_code=FR")
    )
    country_html = by_country.content.decode()
    assert by_country.status_code == 200
    assert "Programmation" in country_html
    assert "SAS belge" not in country_html

    by_category = client.get(
        _url("add_data_references", organization, f"category__id__exact={france.pk}")
    )
    category_html = by_category.content.decode()
    assert by_category.status_code == 200
    assert "Programmation" in category_html
    assert "SAS belge" not in category_html

    by_search = client.get(_url("add_data_references", organization, "q=belge"))
    search_html = by_search.content.decode()
    assert by_search.status_code == 200
    assert "SAS belge" in search_html
    assert "Programmation" not in search_html


@pytest.mark.django_db
def test_add_reference_data_starts_from_the_default_and_accepts_a_change():
    organization = _organization()
    client, _user = _client()
    category = OrganizationAtlasReferenceCategory.objects.create(
        name="Decisions",
        country_code="FR",
    )
    reference = OrganizationAtlasReference.objects.create(
        category=category,
        code="ORDINARY_MAJORITY",
        description="Majorité des décisions ordinaires",
        default_value="50%",
        source="organizationatlas",
        country_code="FR",
    )
    OrganizationAtlasReference.objects.create(
        category=OrganizationAtlasReferenceCategory.for_name(
            "ORDINARY_MAJORITY", "FR",
        ),
        code="66.%",
        source="organizationatlas",
        country_code="FR",
    )
    add_url = _url("add_reference_data", organization, f"reference={reference.pk}")

    page = client.get(add_url)
    assert page.status_code == 200
    html = page.content.decode()
    assert "Majorité des décisions ordinaires" in html
    assert "ORDINARY_MAJORITY" in html
    assert "FR/Decisions" in html
    assert "organizationatlas" in html
    assert 'name="value"' in html
    assert 'value="50%"' in html
    assert 'name="valid_from"' in html
    assert 'name="valid_to"' in html
    assert timezone.localdate().isoformat() in html
    assert 'name="code"' not in html
    assert 'name="description"' not in html
    assert organization.rule_value("FR/DECISIONS", "ORDINARY_MAJORITY") == "50%"

    rejected = client.post(
        add_url,
        {"value": "66%", "valid_from": "2024-06-01", "valid_to": "2020-01-01"},
    )
    assert rejected.status_code == 200
    assert not organization.to_organizationatlasdata.exists()

    response = client.post(
        add_url,
        {"value": "66%", "valid_from": "2024-06-01"},
    )
    assert response.status_code == 302

    row = organization.to_organizationatlasdata.get()
    assert row.data_type.data_type == "ORDINARY_MAJORITY"
    assert row.value == "66%"
    assert row.valid_from == date(2024, 6, 1)
    assert row.valid_to is None
    assert list(row.reference.all()) == [reference]
    assert organization.rule_value("FR/DECISIONS", "ORDINARY_MAJORITY") == "66%"


@pytest.mark.django_db
def test_add_reference_data_closes_previous_unique_data():
    organization = _organization()
    client, user = _client()
    category = OrganizationAtlasReferenceCategory.objects.create(name="APE code", country_code="FR")
    data_type = OrganizationAtlasDataType.for_key("ape", category=category)
    reference = OrganizationAtlasReference.objects.create(
        category=category,
        code="6201Z",
        description="Programmation",
        source="INSEE",
        country_code="FR",
    )
    previous = OrganizationAtlasData.objects.create(
        organization=organization,
        data_type=data_type,
        value="6201Z",
        source=str(user.pk),
        country_code=USER_COUNTRY_CODE,
    )

    add_url = _url("add_reference_data", organization, f"reference={reference.pk}")
    response = client.post(
        add_url,
        {"value": "6201Z"},
        follow=True,
    )

    assert response.status_code == 200
    previous.refresh_from_db()
    assert previous.valid_to == timezone.localdate()
    assert organization.to_organizationatlasdata.count() == 2
    assert "Data added." in response.content.decode()


@pytest.mark.django_db
def test_company_rules_have_distinct_data_types_and_main_values():
    base = fixtures_root() / 'europe' / 'france'
    import_csv_file(base / 'list_cat.csv')
    import_csv_file(base / 'company_rules_ref.csv')
    organization = _organization()
    client, _user = _client()

    for code in ('QUORUM', 'VOTE_METHOD'):
        reference = OrganizationAtlasReference.objects.get(
            category__name='Decisions', code=code,
        )
        assert reference.default_value == 'to complete'
        response = client.post(
            _url('add_reference_data', organization, f'reference={reference.pk}'),
            {'value': code, 'main': 'on'},
        )
        assert response.status_code == 302
        data = organization.to_organizationatlasdata.get(
            data_type__data_type=code,
        )
        assert data.data_type.category == reference.category
        assert data.main is True
