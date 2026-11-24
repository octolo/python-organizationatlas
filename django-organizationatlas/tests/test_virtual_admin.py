from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.contrib import admin
from django.contrib.auth.models import Permission, User
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.http import Http404
from django.test import Client, RequestFactory
from django.urls import reverse
from django.utils.html import escape
from django.utils.http import urlencode

from django_organizationatlas.admin.virtuals.organization import (
    OrganizationAtlasVirtualOrganizationAdmin,
)
from django_organizationatlas.models import (
    OrganizationAtlasData,
    OrganizationAtlasDataType,
    OrganizationAtlasOrganization,
)
from django_organizationatlas.models.virtuals.organization import (
    OrganizationAtlasVirtualOrganization,
)


def _admin():
    return OrganizationAtlasVirtualOrganizationAdmin(
        OrganizationAtlasVirtualOrganization,
        admin.site,
    )


@pytest.mark.django_db
def test_organization_admin_counts_and_filters_shared_codes():
    original = OrganizationAtlasOrganization.objects.create(
        denomination='Original', code='1 & 2', source='test', country_code='FR',
    )
    duplicate = OrganizationAtlasOrganization.objects.create(
        denomination='Copy', code=original.code, source='test', country_code='FR',
        is_duplicate=True,
    )
    foreign = OrganizationAtlasOrganization.objects.create(
        denomination='Foreign', code=original.code, source='test', country_code='BE',
    )
    unique = OrganizationAtlasOrganization.objects.create(
        denomination='Unique', code='1 & 20', source='test', country_code='FR',
    )
    client = Client()
    user = User.objects.create_superuser('admin', password='password')
    client.force_login(user)
    url = reverse(
        'admin:django_organizationatlas_organizationatlasorganization_changelist',
    )

    page = client.get(url, {'q': 'Original'})
    results = list(page.context['cl'].result_list)
    assert len(results) == 1
    assert results[0].sql_same_code_count == 3
    link = f'{url}?{urlencode({"code__exact": original.code})}'
    assert f'href="{escape(link)}">3</a>' in page.content.decode()

    by_code = client.get(link)
    assert {row.pk for row in by_code.context['cl'].result_list} == {
        original.pk, duplicate.pk, foreign.pk,
    }
    shared = client.get(url, {'shared_code': 'yes'})
    assert {row.pk for row in shared.context['cl'].result_list} == {
        original.pk, duplicate.pk, foreign.pk,
    }
    single = client.get(url, {'shared_code': 'no'})
    assert {row.pk for row in single.context['cl'].result_list} == {unique.pk}
    assert single.context['cl'].result_list[0].sql_same_code_count == 1
    unique_link = f'{url}?{urlencode({"code__exact": unique.code})}'
    assert f'href="{escape(unique_link)}">1</a>' in single.content.decode()


@pytest.mark.django_db
def test_organization_admin_shows_code_under_name_and_duplicate_column():
    original = OrganizationAtlasOrganization.objects.create(
        denomination='Original', code='1 & 2', source='test', country_code='FR',
    )
    duplicate = OrganizationAtlasOrganization.objects.create(
        denomination='<Copy>', code=original.code, source='test', country_code='FR',
        is_duplicate=True,
    )
    client = Client()
    user = User.objects.create_superuser('admin', password='password')
    client.force_login(user)
    url = reverse(
        'admin:django_organizationatlas_organizationatlasorganization_changelist',
    )

    content = client.get(url).content.decode()
    original_url = reverse(
        'admin:django_organizationatlas_organizationatlasorganization_change',
        args=[original.pk],
    )
    duplicate_url = reverse(
        'admin:django_organizationatlas_organizationatlasorganization_change',
        args=[duplicate.pk],
    )
    code = '<br><small class="help">1 &amp; 2</small></a>'
    assert f'href="{original_url}">Original{code}' in content
    assert f'href="{duplicate_url}">&lt;Copy&gt;{code}' in content
    assert 'column-duplicate_display' in content
    assert 'column-same_code_count' not in content
    link = escape(f'{url}?{urlencode({"code__exact": original.code})}')
    for icon, alt in (('yes', 'Yes'), ('no', 'No')):
        assert (
            '<td class="field-duplicate_display">'
            f'<img src="/static/admin/img/icon-{icon}.svg" alt="{alt}"> '
            f'<a href="{link}">2</a></td>'
        ) in content
    assert 'boost-label secondary small' not in content


@pytest.mark.django_db
def test_empty_organization_search_links_to_same_virtual_search():
    client = Client()
    user = User.objects.create_superuser('admin', password='password')
    client.force_login(user)
    changelist = reverse(
        'admin:django_organizationatlas_organizationatlasorganization_changelist',
    )
    virtual = reverse(
        'admin:django_organizationatlas_'
        'organizationatlasvirtualorganization_changelist',
    )
    search = 'Société & <test> + 42'

    response = client.get(changelist, {'q': search})

    assert response.status_code == 200
    expected = f'{virtual}?{urlencode({"q": search})}'
    assert f'href="{escape(expected)}"' in response.content.decode()
    assert 'No organization found.' in response.content.decode()
    manager = OrganizationAtlasVirtualOrganization.objects
    with patch.object(manager, 'search_organization', return_value=manager.none()) as mocked:
        target = client.get(expected)
    assert target.status_code == 200
    mocked.assert_called_once_with(query=search, first=False)


@pytest.mark.django_db
def test_search_link_is_absent_for_matches_empty_queries_and_popups():
    OrganizationAtlasOrganization.objects.create(
        denomination='Octolo', code='1', source='test', country_code='FR',
    )
    client = Client()
    user = User.objects.create_superuser('admin', password='password')
    client.force_login(user)
    changelist = reverse(
        'admin:django_organizationatlas_organizationatlasorganization_changelist',
    )
    for query in ({'q': 'Octolo'}, {}, {'q': '  '}, {'q': 'missing', '_popup': '1'}):
        response = client.get(changelist, query)
        assert response.status_code == 200
        assert 'No organization found.' not in response.content.decode()


@pytest.mark.django_db
def test_search_link_requires_virtual_view_permission():
    client = Client()
    user = User.objects.create_user('viewer', password='password', is_staff=True)
    user.user_permissions.add(
        Permission.objects.get(
            content_type__app_label='django_organizationatlas',
            codename='view_organizationatlasorganization',
        ),
    )
    client.force_login(user)
    changelist = reverse(
        'admin:django_organizationatlas_organizationatlasorganization_changelist',
    )

    response = client.get(changelist, {'q': 'missing'})

    assert response.status_code == 200
    assert 'No organization found.' not in response.content.decode()


@pytest.mark.django_db
def test_create_organization_requires_add_permission():
    request = RequestFactory().post("/")
    request.user = User.objects.create_user("viewer", password="password")
    model_admin = _admin()

    with pytest.raises(PermissionDenied):
        model_admin.handle_create_organization(request, "917432254")


@pytest.mark.django_db
def test_show_organization_redirects_to_persisted_primary_key():
    organization = OrganizationAtlasOrganization.objects.create(
        denomination="Octolo",
        code="internal-code",
        source="insee",
        country_code="FR",
    )
    OrganizationAtlasData.objects.create(
        organization=organization,
        data_type=OrganizationAtlasDataType.for_key("siren"),
        value="917432254",
        source="insee",
        country_code="FR",
    )
    virtual = SimpleNamespace(source_field="siren", reference="917432254")
    model_admin = _admin()
    model_admin.get_object = lambda request, object_id: virtual

    response = model_admin.handle_show_organization(
        RequestFactory().get("/"),
        "917432254",
    )

    assert response.url == reverse(
        "admin:django_organizationatlas_organizationatlasorganization_change",
        args=[organization.pk],
    )


@pytest.mark.django_db
def test_create_organization_rejects_existing_reference():
    organization = OrganizationAtlasOrganization.objects.create(
        denomination="Octolo",
        code="917432254",
        source="insee",
        country_code="FR",
    )
    OrganizationAtlasData.objects.create(
        organization=organization,
        data_type=OrganizationAtlasDataType.for_key("siren"),
        value="917432254",
        source="insee",
        country_code="FR",
    )
    virtual = SimpleNamespace(source_field="siren", reference="917432254")
    request = RequestFactory().post("/")
    request.user = User.objects.create_superuser("admin", password="password")
    model_admin = _admin()
    model_admin.get_object = lambda request, object_id: virtual

    with pytest.raises(PermissionDenied):
        model_admin.handle_create_organization(request, "917432254")


@pytest.mark.django_db
def test_create_organization_returns_404_when_reference_disappeared():
    request = RequestFactory().post("/")
    request.user = User.objects.create_superuser("admin", password="password")
    model_admin = _admin()
    model_admin.get_object = lambda request, object_id: None

    with pytest.raises(Http404):
        model_admin.handle_create_organization(request, "917432254")


@pytest.mark.django_db
def test_duplicate_creates_provider_data_without_copying_local_data():
    original = OrganizationAtlasOrganization.objects.create(
        denomination='Octolo', code='917432254', source='insee',
        country_code='FR',
    )
    OrganizationAtlasData.objects.create(
        organization=original,
        data_type=OrganizationAtlasDataType.for_key('siren'),
        value='917432254', source='insee', country_code='FR',
    )
    OrganizationAtlasData.objects.create(
        organization=original,
        data_type=OrganizationAtlasDataType.for_key('local_only'),
        value='private', source='user', country_code='FR',
    )
    virtual = OrganizationAtlasVirtualOrganization(
        organizationatlas_id='insee-917432254',
        denomination='Octolo',
        reference='917432254',
        source_field='siren',
        backend='insee',
        country_code='FR',
        address_json=None,
        data_source=None,
    )
    client = Client()
    user = User.objects.create_superuser('admin', password='password')
    client.force_login(user)
    url = reverse(
        'admin:django_organizationatlas_'
        'organizationatlasvirtualorganization_change',
        args=[virtual.pk],
    )

    with patch.object(
        OrganizationAtlasVirtualOrganizationAdmin,
        'get_object',
        return_value=virtual,
    ):
        page = client.get(url)
        assert 'Duplicate Organization' in page.content.decode()
        assert 'Show Organization' in page.content.decode()
        response = client.post(url, {'duplicate_organization': '1'})

    assert response.status_code == 302
    duplicate = OrganizationAtlasOrganization.objects.get(is_duplicate=True)
    assert response.url.endswith(f'/{duplicate.pk}/change/')
    assert duplicate.code == original.code
    assert duplicate.country_code == original.country_code
    assert duplicate.named_id != original.named_id
    assert duplicate.to_organizationatlasdata.filter(
        data_type__data_type='siren', value='917432254',
    ).exists()
    assert not duplicate.to_organizationatlasdata.filter(
        data_type__data_type='local_only',
    ).exists()
    assert duplicate.history.first().is_duplicate
    with patch.object(
        OrganizationAtlasVirtualOrganizationAdmin,
        'get_object',
        return_value=virtual,
    ):
        page = client.get(url)
        assert 'Show Organizations' in page.content.decode()
        assert 'Duplicate Organization' in page.content.decode()
        response = client.post(url, {'duplicate_organization': '1'})
    assert response.status_code == 302
    assert (
        OrganizationAtlasOrganization.objects.filter(is_duplicate=True).count()
        == 2
    )


@pytest.mark.django_db
def test_duplicate_requires_existing_organization_and_add_permission():
    model_admin = _admin()
    virtual = SimpleNamespace(source_field='siren', reference='1')
    request = RequestFactory().post('/')
    request.user = User.objects.create_user('viewer', password='password')
    model_admin.get_object = lambda request, object_id: virtual

    with pytest.raises(PermissionDenied):
        model_admin.handle_duplicate_organization(request, '1')
    request.user = User.objects.create_superuser('admin', password='password')
    with pytest.raises(PermissionDenied):
        model_admin.handle_duplicate_organization(request, '1')


@pytest.mark.django_db
def test_duplicate_requires_permission_to_view_virtual_organization():
    original = OrganizationAtlasOrganization.objects.create(
        denomination='Octolo', code='1', source='insee', country_code='FR',
    )
    OrganizationAtlasData.objects.create(
        organization=original,
        data_type=OrganizationAtlasDataType.for_key('siren'),
        value='1', source='insee', country_code='FR',
    )
    request = RequestFactory().post('/')
    request.user = User.objects.create_user(
        'adder', password='password', is_staff=True,
    )
    request.user.user_permissions.add(
        Permission.objects.get(
            content_type__app_label='django_organizationatlas',
            codename='add_organizationatlasorganization',
        ),
    )
    model_admin = _admin()
    model_admin.get_object = lambda request, object_id: SimpleNamespace(
        source_field='siren', reference='1',
    )
    with pytest.raises(PermissionDenied):
        model_admin.handle_duplicate_organization(request, '1')


@pytest.mark.django_db
def test_original_is_unique_and_duplicate_named_ids_fit():
    values = {
        'denomination': 'Long organization name that fills the identifier',
        'code': '917432254',
        'source': 'insee',
        'country_code': 'FR',
    }
    original = OrganizationAtlasOrganization.objects.create(**values)
    copies = [
        OrganizationAtlasOrganization.objects.create(**values, is_duplicate=True)
        for _ in range(3)
    ]
    named_ids = [original.named_id, *(copy.named_id for copy in copies)]
    assert len(set(named_ids)) == 4
    assert all(len(named_id) <= 40 for named_id in named_ids)
    previous = copies[0].named_id
    copies[0].save()
    assert copies[0].named_id == previous
    with pytest.raises(IntegrityError), transaction.atomic():
        OrganizationAtlasOrganization.objects.create(**values)
