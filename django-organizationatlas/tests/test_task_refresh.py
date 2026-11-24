from datetime import date, timedelta
from importlib import import_module
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.urls import reverse

from django_organizationatlas.models import (
    OrganizationAtlasData,
    OrganizationAtlasDataType,
    OrganizationAtlasOrganization,
    OrganizationAtlasReference,
    OrganizationAtlasReferenceCategory,
)
from django_organizationatlas.services.refresh import (
    load_history_from_providers,
    preferred_data,
    refresh_from_providers,
)
from django_organizationatlas.task import get_task_backend
from django_organizationatlas.task.refresh import (
    enqueue_refresh_all_organizations,
    refresh_all_organizations,
)


def _provider(name, priority, history=False):
    provider = SimpleNamespace(
        name=name,
        display_name=name.upper(),
        priority=priority,
        geo_code='FR',
        search_organization_by_reference=lambda: None,
    )
    if history:
        provider.get_organization_history = lambda: None
    return provider


def _virtual(source, denomination, ape):
    values = {
        'backend': source.upper(),
        'country_code': 'FR',
        'reference': '123',
        'denomination': denomination,
        'ape': ape,
        'data_source': None,
        'address_json': None,
    }
    obj = SimpleNamespace(**values)
    obj._meta = SimpleNamespace(
        get_fields=lambda: [SimpleNamespace(name=name) for name in values],
    )
    return obj


@pytest.mark.django_db
def test_refresh_merges_equal_normalized_values_and_records_sources():
    organization = OrganizationAtlasOrganization.objects.create(
        denomination='Old', code='123', source='manual', country_code='FR',
    )
    reference = OrganizationAtlasReference.objects.create(
        category=OrganizationAtlasReferenceCategory.for_name('ape', 'FR'),
        code='62.01Z',
        source='reference',
        country_code='FR',
    )
    providers = [_provider('first', 5), _provider('second', 3)]
    results = {
        'first': _virtual('first', 'Same', '6201Z'),
        'second': _virtual('second', 'Same', '62.01Z'),
    }
    with (
        patch(
            'django_organizationatlas.services.refresh.available_providers',
            return_value=providers,
        ),
        patch(
            'django_organizationatlas.services.refresh.fetch_organization_for_refresh',
            side_effect=lambda _code, name: results[name],
        ),
    ):
        assert refresh_from_providers(organization)['errors'] == []
        rows = organization.to_organizationatlasdata.filter(
            data_type__data_type='ape', valid_to__isnull=True,
        )
        row = rows.get()
        assert row.value == '62.01Z'
        assert list(row.reference.all()) == [reference]
        assert set(row.metadata['provider_observations']) == {
            'FIRST', 'SECOND',
        }
        updated_at = row.updated_at
        refresh_from_providers(organization)
        row.refresh_from_db()
        assert rows.count() == 1
        assert row.updated_at == updated_at


@pytest.mark.django_db
def test_preferred_data_keeps_same_code_for_each_country():
    organization = OrganizationAtlasOrganization.objects.create(
        denomination='Octolo', code='1', source='source', country_code='FR',
    )
    french_type = OrganizationAtlasDataType.for_key(
        'activity',
        category=OrganizationAtlasReferenceCategory.for_name('Activity', 'FR'),
    )
    belgian_type = OrganizationAtlasDataType.for_key(
        'activity',
        category=OrganizationAtlasReferenceCategory.for_name('Activity', 'BE'),
    )
    french = OrganizationAtlasData.objects.create(
        organization=organization, data_type=french_type, value='fr',
        country_code='FR', source='source',
    )
    belgian = OrganizationAtlasData.objects.create(
        organization=organization, data_type=belgian_type, value='be',
        country_code='BE', source='source',
    )

    assert preferred_data(organization, {}) == {
        ('FR', 'activity'): french,
        ('BE', 'activity'): belgian,
    }


@pytest.mark.django_db
def test_refresh_preserves_unselected_observations_and_historizes_changes():
    organization = OrganizationAtlasOrganization.objects.create(
        denomination='Old', code='123', source='manual', country_code='FR',
    )
    providers = [_provider('first', 5), _provider('second', 3)]
    results = {
        'first': _virtual('first', 'Same', '11'),
        'second': _virtual('second', 'Same', '22'),
    }
    with (
        patch(
            'django_organizationatlas.services.refresh.available_providers',
            return_value=providers,
        ),
        patch(
            'django_organizationatlas.services.refresh.fetch_organization_for_refresh',
            side_effect=lambda _code, name: results[name],
        ),
    ):
        refresh_from_providers(organization)
        old = organization.to_organizationatlasdata.get(
            data_type__data_type='ape', valid_to__isnull=True,
        )
        old.valid_from = date.today() - timedelta(days=2)
        old.save(update_fields=['valid_from'])
        results['first'].ape = '33'
        refresh_from_providers(organization, ['first'])

    old.refresh_from_db()
    current = organization.to_organizationatlasdata.get(
        data_type__data_type='ape', valid_to__isnull=True,
    )
    assert old.value == '11'
    assert old.valid_to == date.today() - timedelta(days=1)
    assert current.value == '33'
    assert current.metadata['provider_observations']['SECOND']['value'] == '22'


@pytest.mark.django_db
def test_refresh_keeps_existing_duplicates_without_adding_another():
    organization = OrganizationAtlasOrganization.objects.create(
        denomination='Old', code='123', source='manual', country_code='FR',
    )
    datatype = OrganizationAtlasDataType.for_key('ape')
    existing = [
        OrganizationAtlasData.objects.create(
            organization=organization,
            data_type=datatype,
            source=source,
            country_code='FR',
            value='11',
        )
        for source in ('FIRST', 'SECOND')
    ]
    providers = [
        _provider('first', 5),
        _provider('second', 3),
        _provider('third', 1),
    ]
    with (
        patch(
            'django_organizationatlas.services.refresh.available_providers',
            return_value=providers,
        ),
        patch(
            'django_organizationatlas.services.refresh.fetch_organization_for_refresh',
            side_effect=lambda _code, name: _virtual(name, 'Same', '11'),
        ),
    ):
        assert refresh_from_providers(organization)['errors'] == []
    rows = organization.to_organizationatlasdata.filter(
        data_type=datatype, valid_to__isnull=True,
    )
    assert set(rows.values_list('pk', flat=True)) == {
        row.pk for row in existing
    }


@pytest.mark.django_db
def test_refresh_uses_known_date_then_keeps_other_provider_as_fallback():
    organization = OrganizationAtlasOrganization.objects.create(
        denomination='Old', code='123', source='manual', country_code='FR',
    )
    providers = [
        _provider('first', 5, history=True),
        _provider('second', 3, history=True),
    ]
    results = {
        'first': _virtual('first', 'Same', '11'),
        'second': _virtual('second', 'Same', '22'),
    }
    history = {
        'first': [
            {'field': 'ape', 'value': '11', 'valid_from': '2020-01-01'},
        ],
        'second': [
            {'field': 'ape', 'value': '22', 'valid_from': '2019-01-01'},
        ],
    }
    with (
        patch(
            'django_organizationatlas.services.refresh.available_providers',
            return_value=providers,
        ),
        patch(
            'django_organizationatlas.services.refresh.fetch_organization_for_refresh',
            side_effect=lambda _code, name: results[name],
        ),
        patch(
            'django_organizationatlas.services.refresh.fetch_organization_history',
            side_effect=lambda _code, name: history[name],
        ),
    ):
        refresh_from_providers(organization)
        row = organization.to_organizationatlasdata.get(
            data_type__data_type='ape', valid_to__isnull=True,
        )
        assert (row.source, row.value) == ('FIRST', '11')
        results['first'].ape = '33'
        history['first'] = []
        refresh_from_providers(organization, ['first'])
        row.refresh_from_db()
        assert (row.source, row.value) == ('SECOND', '22')
        assert row.metadata['provider_observations']['SECOND']['value'] == '22'
        assert row.metadata['provider_observations']['FIRST']['valid_from'] is None


@pytest.mark.django_db
def test_refresh_compares_the_final_merge_before_creating_history():
    organization = OrganizationAtlasOrganization.objects.create(
        denomination='Old', code='123', source='manual', country_code='FR',
    )
    providers = [
        _provider('first', 5, history=True),
        _provider('second', 3, history=True),
    ]
    results = {
        'first': _virtual('first', 'Same', '11'),
        'second': _virtual('second', 'Same', '22'),
    }
    history = {
        'first': [{'field': 'ape', 'value': '11', 'valid_from': '2020-01-01'}],
        'second': [{'field': 'ape', 'value': '22', 'valid_from': '2019-01-01'}],
    }
    with (
        patch(
            'django_organizationatlas.services.refresh.available_providers',
            return_value=providers,
        ),
        patch(
            'django_organizationatlas.services.refresh.fetch_organization_for_refresh',
            side_effect=lambda _code, name: results[name],
        ),
        patch(
            'django_organizationatlas.services.refresh.fetch_organization_history',
            side_effect=lambda _code, name: history[name],
        ),
    ):
        refresh_from_providers(organization)
        old = organization.to_organizationatlasdata.get(
            data_type__data_type='ape', valid_to__isnull=True,
        )
        old.valid_from = date(2020, 1, 1)
        old.save(update_fields=['valid_from'])
        results['first'].ape = '33'
        history['first'] = []
        results['second'].ape = '11'
        history['second'] = [
            {'field': 'ape', 'value': '11', 'valid_from': '2021-01-01'},
        ]
        refresh_from_providers(organization)

    rows = organization.to_organizationatlasdata.filter(
        data_type__data_type='ape',
    )
    assert rows.count() == 1
    old.refresh_from_db()
    assert (old.value, old.source, old.valid_to) == ('11', 'SECOND', None)


@pytest.mark.django_db
def test_history_does_not_duplicate_a_merged_current_value():
    organization = OrganizationAtlasOrganization.objects.create(
        denomination='Old', code='123', source='manual', country_code='FR',
    )
    providers = [
        _provider('first', 5, history=True),
        _provider('second', 3, history=True),
    ]
    history = [
        {'field': 'ape', 'value': '11', 'valid_from': '2020-01-01'},
    ]
    with (
        patch(
            'django_organizationatlas.services.refresh.available_providers',
            return_value=providers,
        ),
        patch(
            'django_organizationatlas.services.refresh.fetch_organization_for_refresh',
            side_effect=lambda _code, name: _virtual(name, 'Same', '11'),
        ),
        patch(
            'django_organizationatlas.services.refresh.fetch_organization_history',
            return_value=history,
        ),
    ):
        refresh_all_organizations(actions=['refresh', 'history'])

    rows = organization.to_organizationatlasdata.filter(
        data_type__data_type='ape', valid_to__isnull=True,
    )
    assert rows.count() == 1, list(
        rows.values_list('source', 'value', 'metadata')
    )
    row = rows.get()
    assert set(row.metadata['provider_observations']) == {'FIRST', 'SECOND'}


@pytest.mark.django_db
def test_history_date_can_promote_a_previously_unselected_observation():
    organization = OrganizationAtlasOrganization.objects.create(
        denomination='Old', code='123', source='manual', country_code='FR',
    )
    providers = [_provider('first', 5), _provider('second', 3, history=True)]
    results = {
        'first': _virtual('first', 'Same', '11'),
        'second': _virtual('second', 'Same', '22'),
    }
    with (
        patch(
            'django_organizationatlas.services.refresh.available_providers',
            return_value=providers,
        ),
        patch(
            'django_organizationatlas.services.refresh.fetch_organization_for_refresh',
            side_effect=lambda _code, name: results[name],
        ),
        patch(
            'django_organizationatlas.services.refresh.fetch_organization_history',
            return_value=[],
        ) as fetch_history,
    ):
        refresh_from_providers(organization)
        fetch_history.return_value = [
            {'field': 'ape', 'value': '22', 'valid_from': '2020-01-01'},
        ]
        assert load_history_from_providers(
            organization, ['second']
        )['errors'] == []
        row = organization.to_organizationatlasdata.get(
            data_type__data_type='ape', valid_to__isnull=True,
        )
        assert (row.source, row.value) == ('SECOND', '22')
        assert row.valid_from == date(2020, 1, 1)
        assert preferred_data(organization)['FR', 'ape'].pk == row.pk


@pytest.mark.django_db
def test_refresh_merges_sources_and_prefers_known_date():
    organization = OrganizationAtlasOrganization.objects.create(
        denomination='Old',
        code='123',
        source='manual',
        country_code='FR',
    )
    providers = [_provider('first', 5), _provider('second', 3, history=True)]
    results = {
        'first': _virtual('first', 'Undated', '11.11A'),
        'second': _virtual('second', 'Dated', '22.22B'),
    }
    history = [
        {'field': 'denomination', 'value': 'Dated', 'valid_from': '2020-01-01'},
    ]
    with (
        patch(
            'django_organizationatlas.services.refresh.available_providers',
            return_value=providers,
        ),
        patch(
            'django_organizationatlas.services.refresh.fetch_organization_for_refresh',
            side_effect=lambda _code, name: results[name],
        ),
        patch(
            'django_organizationatlas.services.refresh.fetch_organization_history',
            return_value=history,
        ),
    ):
        report = refresh_from_providers(organization, [])
        assert report == {'refreshed': ['first', 'second'], 'errors': []}
        organization.refresh_from_db()
        assert organization.denomination == 'Dated'
        assert organization.code == '123'
        assert organization.source == 'manual'
        ape = organization.to_organizationatlasdata.get(
            data_type__data_type='ape', valid_to__isnull=True,
        )
        assert (ape.source, ape.value) == ('FIRST', '11.11A')
        assert ape.metadata['provider_observations']['SECOND']['value'] == (
            '22.22B'
        )
        assert preferred_data(organization)['FR', 'ape'].source == 'FIRST'
        assert (
            preferred_data(organization)['FR', 'denomination'].source
            == 'SECOND'
        )
        count = organization.to_organizationatlasdata.count()
        before = dict(
            organization.to_organizationatlasdata.values_list(
                'pk', 'updated_at'
            )
        )
        organization_updated_at = organization.updated_at
        refresh_from_providers(organization, [])
        assert organization.to_organizationatlasdata.count() == count
        assert (
            dict(
                organization.to_organizationatlasdata.values_list(
                    'pk', 'updated_at'
                )
            )
            == before
        )
        organization.refresh_from_db()
        assert organization.updated_at == organization_updated_at
        old = organization.to_organizationatlasdata.get(
            source='FIRST',
            data_type__data_type='ape',
            valid_to__isnull=True,
        )
        old.valid_from = date.today() - timedelta(days=2)
        old.save(update_fields=['valid_from'])
        results['first'].ape = '33.33C'
        refresh_from_providers(organization, ['first'])
        old.refresh_from_db()
        assert old.valid_to == date.today() - timedelta(days=1)
        assert (
            organization.to_organizationatlasdata.get(
                source='FIRST',
                data_type__data_type='ape',
                valid_to__isnull=True,
            ).value
            == '33.33C'
        )


@pytest.mark.django_db
def test_refresh_priority_breaks_unknown_date_ties():
    organization = OrganizationAtlasOrganization.objects.create(
        denomination='Old',
        code='123',
        source='manual',
        country_code='FR',
    )
    providers = [_provider('low', 1), _provider('high', 5)]
    with (
        patch(
            'django_organizationatlas.services.refresh.available_providers',
            return_value=providers,
        ),
        patch(
            'django_organizationatlas.services.refresh.fetch_organization_for_refresh',
            side_effect=lambda _code, name: _virtual(name, name, '11'),
        ),
    ):
        refresh_from_providers(organization)
    organization.refresh_from_db()
    assert organization.denomination == 'high'


@pytest.mark.django_db
def test_headquarters_uses_dated_provider_before_higher_priority():
    organization = OrganizationAtlasOrganization.objects.create(
        denomination='Old',
        code='123',
        source='manual',
        country_code='FR',
    )
    providers = [_provider('first', 5), _provider('second', 3, history=True)]
    first = _virtual('first', 'Same', '11')
    second = _virtual('second', 'Same', '11')
    first.address_json = {'address_line1': 'First street'}
    second.address_json = {'address_line1': 'Second street'}
    second.address = 'Second street'
    history = [
        {
            'field': 'address',
            'value': 'Second street',
            'valid_from': '2020-01-01',
        },
    ]
    with (
        patch(
            'django_organizationatlas.services.refresh.available_providers',
            return_value=providers,
        ),
        patch(
            'django_organizationatlas.services.refresh.fetch_organization_for_refresh',
            side_effect=lambda _code, name: {'first': first, 'second': second}[
                name
            ],
        ),
        patch(
            'django_organizationatlas.services.refresh.fetch_organization_history',
            return_value=history,
        ),
    ):
        refresh_from_providers(organization)
        assert organization.headquarters_address.source == 'SECOND'
        assert (
            organization.to_organizationatlasaddress.filter(
                valid_to__isnull=True,
            ).count()
            == 2
        )
        refresh_from_providers(organization)
        assert organization.to_organizationatlasaddress.count() == 2


@pytest.mark.django_db
def test_refresh_reports_errors_and_continues():
    organization = OrganizationAtlasOrganization.objects.create(
        denomination='Old',
        code='123',
        source='manual',
        country_code='FR',
    )
    providers = [_provider('broken', 5), _provider('working', 1)]
    with (
        patch(
            'django_organizationatlas.services.refresh.available_providers',
            return_value=providers,
        ),
        patch(
            'django_organizationatlas.services.refresh.fetch_organization_for_refresh',
            side_effect=[
                RuntimeError('sensitive'),
                _virtual('working', 'Good', '11'),
            ],
        ),
    ):
        report = refresh_from_providers(organization)
    assert report == {
        'refreshed': ['working'],
        'errors': ['broken: refresh failed'],
    }
    organization.refresh_from_db()
    assert organization.denomination == 'Good'


@pytest.mark.django_db
def test_admin_refresh_allows_multiple_providers_and_empty_selection(client):
    user = get_user_model().objects.create_superuser(
        username='admin',
        email='admin@example.com',
        password='test',
    )
    client.force_login(user)
    organization = OrganizationAtlasOrganization.objects.create(
        denomination='Old',
        code='123',
        source='manual',
        country_code='FR',
    )
    url = reverse(
        'admin:django_organizationatlas_organizationatlasorganization_refresh',
        args=[organization.pk],
    )
    response = client.get(url)
    assert response.status_code == 200
    html = response.content.decode()
    assert 'name="providers"' in html
    assert 'name="enqueue"' in html
    assert 'class="selectfilter"' in html
    assert 'multiple' in html
    assert 'admin/css/forms.css' in html
    assert 'admin/js/core.js' in html
    assert 'admin/js/SelectBox.js' in html
    assert 'admin/js/SelectFilter2.js' in html
    assert html.index(reverse('admin:jsi18n')) < html.index(
        'admin/js/SelectFilter2.js'
    )
    with patch(
        'django_organizationatlas.admin.organization.refresh_from_providers',
        return_value={'refreshed': ['insee'], 'errors': []},
    ) as refresh:
        response = client.post(url, {'providers': ['insee', 'inpi']})
        assert response.status_code == 302
        assert refresh.call_args.args[1] == ['insee', 'inpi']
        response = client.post(url, {})
        assert response.status_code == 302
        assert refresh.call_args.args[1] == []
    with patch(
        'django_organizationatlas.admin.organization.enqueue_refresh_one_organization',
    ) as enqueue:
        response = client.post(url, {'providers': ['insee'], 'enqueue': 'on'})
    assert response.status_code == 302
    enqueue.assert_called_once_with(organization.pk, ['insee'])


@pytest.mark.django_db
def test_refresh_all_continues_and_reports_errors():
    for code in ('1', '2'):
        OrganizationAtlasOrganization.objects.create(
            denomination=code,
            code=code,
            source='manual',
            country_code='FR',
        )
    with patch(
        'django_organizationatlas.task.refresh.refresh_from_providers',
        side_effect=[
            {'refreshed': [], 'errors': ['failure']},
            {'refreshed': ['ok'], 'errors': []},
        ],
    ) as refresh:
        with pytest.raises(RuntimeError, match='1 organization'):
            refresh_all_organizations(['insee'])
        assert refresh.call_count == 2


def test_sync_backend_and_unknown_backend(settings):
    settings.ORGANIZATIONATLAS_TASK_BACKEND = 'sync'
    assert get_task_backend().enqueue(str.upper, 'ok') == 'OK'
    settings.ORGANIZATIONATLAS_TASK_BACKEND = 'unknown'
    with pytest.raises(ImproperlyConfigured):
        get_task_backend()


def test_thread_backend_executes_callable(settings):
    settings.ORGANIZATIONATLAS_TASK_BACKEND = 'thread'
    callback = MagicMock()
    thread = get_task_backend().enqueue(callback, 'value')
    thread.join(timeout=5)
    assert not thread.is_alive()
    callback.assert_called_once_with('value')


def test_celery_backend_dispatches_importable_callable(settings):
    pytest.importorskip('celery')
    from django_organizationatlas.task.celery import celery_enqueue_task

    settings.ORGANIZATIONATLAS_TASK_BACKEND = 'celery'
    with patch.object(celery_enqueue_task, 'delay') as delay:
        get_task_backend().enqueue(refresh_all_organizations, None, ['history'])
    delay.assert_called_once_with(
        'django_organizationatlas.task.refresh.refresh_all_organizations',
        [None, ['history']],
        {},
    )


def test_rq_backend_uses_default_queue(settings, monkeypatch):
    queue = MagicMock()
    get_queue = MagicMock(return_value=queue)
    monkeypatch.setitem(
        sys.modules, 'django_rq', SimpleNamespace(get_queue=get_queue)
    )
    module = import_module('django_organizationatlas.task.django_rq')
    monkeypatch.setattr(module, 'django_rq', sys.modules['django_rq'])
    settings.ORGANIZATIONATLAS_TASK_BACKEND = 'rq'
    get_task_backend().enqueue(refresh_all_organizations, None, ['history'])
    get_queue.assert_called_once_with('default')
    queue.enqueue.assert_called_once_with(
        refresh_all_organizations,
        None,
        ['history'],
    )


def test_refresh_enqueue_uses_selected_backend():
    with patch(
        'django_organizationatlas.task.refresh.get_task_backend'
    ) as backend:
        enqueue_refresh_all_organizations(['insee'])
    backend.return_value.enqueue.assert_called_once_with(
        refresh_all_organizations,
        ['insee'],
        ['refresh'],
    )


@pytest.mark.django_db
def test_refresh_and_history_reuse_provider_history():
    organization = OrganizationAtlasOrganization.objects.create(
        denomination='Old',
        code='123',
        source='manual',
        country_code='FR',
    )
    providers = [_provider('second', 3, history=True)]
    history = [
        {
            'field': 'denomination',
            'value': 'Former',
            'valid_from': '2010-01-01',
            'valid_to': '2019-12-31',
        },
        {'field': 'denomination', 'value': 'Dated', 'valid_from': '2020-01-01'},
    ]
    with (
        patch(
            'django_organizationatlas.services.refresh.available_providers',
            return_value=providers,
        ),
        patch(
            'django_organizationatlas.services.refresh.fetch_organization_for_refresh',
            return_value=_virtual('second', 'Dated', '22'),
        ),
        patch(
            'django_organizationatlas.services.refresh.fetch_organization_history',
            return_value=history,
        ) as fetch_history,
    ):
        refresh_all_organizations(['second'], ['refresh', 'history'])
    fetch_history.assert_called_once_with('123', 'second')
    records = organization.to_organizationatlasdata.filter(
        data_type__data_type='denomination',
        source='SECOND',
    ).order_by('valid_from')
    assert list(records.values_list('value', 'valid_to')) == [
        ('Former', date(2019, 12, 31)),
        ('Dated', None),
    ]
    assert records.last().metadata['provider_valid_from'] == '2020-01-01'


@pytest.mark.django_db
def test_history_only_does_not_refresh():
    OrganizationAtlasOrganization.objects.create(
        denomination='Old',
        code='123',
        source='manual',
        country_code='FR',
    )
    providers = [_provider('second', 3, history=True)]
    with (
        patch(
            'django_organizationatlas.services.refresh.available_providers',
            return_value=providers,
        ),
        patch(
            'django_organizationatlas.services.refresh.fetch_organization_for_refresh'
        ) as fetch,
        patch(
            'django_organizationatlas.services.refresh.fetch_organization_history',
            return_value=[],
        ),
    ):
        refresh_all_organizations(actions=['history'])
    fetch.assert_not_called()


@pytest.mark.parametrize('actions', [[], ['person'], ['document'], ['event']])
def test_task_rejects_unsupported_actions(actions):
    with pytest.raises(ValueError, match='refresh and/or history'):
        refresh_all_organizations(actions=actions)
    with pytest.raises(ValueError, match='refresh and/or history'):
        enqueue_refresh_all_organizations(actions=actions)


@pytest.mark.django_db
def test_history_reconciles_an_observed_value_without_changing_it():
    organization = OrganizationAtlasOrganization.objects.create(
        denomination='Dated',
        code='123',
        source='manual',
        country_code='FR',
    )
    providers = [_provider('second', 3, history=True)]
    virtual = _virtual('second', 'Dated', '22')
    history = [
        {'field': 'denomination', 'value': 'Dated', 'valid_from': '2020-01-01'},
    ]
    with (
        patch(
            'django_organizationatlas.services.refresh.available_providers',
            return_value=providers,
        ),
        patch(
            'django_organizationatlas.services.refresh.fetch_organization_for_refresh',
            return_value=virtual,
        ),
        patch(
            'django_organizationatlas.services.refresh.fetch_organization_history',
            return_value=history,
        ),
    ):
        refresh_from_providers(organization)
        row = organization.to_organizationatlasdata.get(
            source='SECOND',
            data_type__data_type='denomination',
        )
        row.valid_from = date.today()
        row.save(update_fields=['valid_from'])
        refresh_all_organizations(['second'], ['history'])
        row.refresh_from_db()
        assert row.valid_from == date(2020, 1, 1)
        updated_at = row.updated_at
        refresh_all_organizations(['second'], ['history'])
        row.refresh_from_db()
        assert row.updated_at == updated_at


@pytest.mark.django_db
def test_refresh_reuses_existing_provider_source_name():
    organization = OrganizationAtlasOrganization.objects.create(
        denomination='Dated',
        code='123',
        source='manual',
        country_code='FR',
    )
    OrganizationAtlasData.objects.create(
        organization=organization,
        source='second',
        country_code='FR',
        data_type=OrganizationAtlasDataType.for_key('denomination'),
        value='Dated',
    )
    providers = [_provider('second', 3, history=True)]
    history = [
        {'field': 'denomination', 'value': 'Dated', 'valid_from': '2020-01-01'},
    ]
    with (
        patch(
            'django_organizationatlas.services.refresh.available_providers',
            return_value=providers,
        ),
        patch(
            'django_organizationatlas.services.refresh.fetch_organization_for_refresh',
            return_value=_virtual('second', 'Dated', '22'),
        ),
        patch(
            'django_organizationatlas.services.refresh.fetch_organization_history',
            return_value=history,
        ),
    ):
        refresh_all_organizations(['second'], ['history', 'refresh'])
    assert set(
        organization.to_organizationatlasdata.values_list(
            'source',
            flat=True,
        )
    ) == {'second'}


@pytest.mark.django_db
def test_refresh_reuses_source_stored_only_in_observations():
    organization = OrganizationAtlasOrganization.objects.create(
        denomination='Same', code='123', source='manual', country_code='FR',
    )
    OrganizationAtlasData.objects.create(
        organization=organization,
        source='first',
        country_code='FR',
        data_type=OrganizationAtlasDataType.for_key('ape'),
        value='11',
    )
    providers = [_provider('first', 1), _provider('second', 5)]
    with (
        patch(
            'django_organizationatlas.services.refresh.available_providers',
            return_value=providers,
        ),
        patch(
            'django_organizationatlas.services.refresh.fetch_organization_for_refresh',
            side_effect=lambda _code, name: _virtual(name, 'Same', '11'),
        ),
    ):
        assert refresh_from_providers(organization)['errors'] == []
        assert refresh_from_providers(organization, ['first'])['errors'] == []
    row = organization.to_organizationatlasdata.get(
        data_type__data_type='ape', valid_to__isnull=True,
    )
    assert set(row.metadata['provider_observations']) == {'first', 'SECOND'}


@pytest.mark.django_db
def test_history_only_provider_does_not_need_reference_search():
    OrganizationAtlasOrganization.objects.create(
        denomination='Dated',
        code='123',
        source='manual',
        country_code='FR',
    )
    provider = _provider('second', 3, history=True)
    provider.search_organization_by_reference = None
    with (
        patch(
            'django_organizationatlas.services.refresh.available_providers',
            return_value=[provider],
        ),
        patch(
            'django_organizationatlas.services.refresh.fetch_organization_history',
            return_value=[],
        ) as fetch_history,
    ):
        refresh_all_organizations(actions=['history'])
    fetch_history.assert_called_once_with('123', 'second')


@pytest.mark.django_db
def test_refresh_reports_conflicting_source_names_without_merging_them():
    organization = OrganizationAtlasOrganization.objects.create(
        denomination='Dated',
        code='123',
        source='manual',
        country_code='FR',
    )
    for source in ('second', 'SECOND'):
        OrganizationAtlasData.objects.create(
            organization=organization,
            source=source,
            country_code='FR',
            data_type=OrganizationAtlasDataType.for_key('denomination'),
            value='Dated',
        )
    providers = [_provider('second', 3)]
    with (
        patch(
            'django_organizationatlas.services.refresh.available_providers',
            return_value=providers,
        ),
        patch(
            'django_organizationatlas.services.refresh.fetch_organization_for_refresh',
            return_value=_virtual('second', 'Changed', '22'),
        ),
    ):
        report = refresh_from_providers(organization)
    assert report == {'refreshed': [], 'errors': ['second: refresh failed']}
    organization.refresh_from_db()
    assert organization.denomination == 'Dated'
