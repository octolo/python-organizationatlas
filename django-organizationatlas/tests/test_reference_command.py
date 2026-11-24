import csv

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.urls import reverse

from django_organizationatlas.models import (
    OrganizationAtlasData,
    OrganizationAtlasDataType,
    OrganizationAtlasOrganization,
    OrganizationAtlasReference,
    OrganizationAtlasReferenceCategory,
)
from django_organizationatlas.services.reference import (
    fixtures_root,
    import_category_rows,
    import_csv_file,
    load_default_references,
    read_csv,
)


def test_read_csv_supports_mixed_columns(tmp_path):
    csv_path = tmp_path / "reference.csv"
    csv_path.write_text(
        "source;description;code;country_code;category\n"
        "sample;Culture du riz;0112Z;FR;ape\n",
        encoding="utf-8",
    )

    assert read_csv(csv_path) == [
        {
            "category": "ape",
            "code": "0112Z",
            "description": "Culture du riz",
            "country_code": "FR",
            "source": "sample",
        }
    ]


def test_reference_fixtures_have_no_uniqueness_column():
    root = fixtures_root()
    required = {'category', 'code', 'description', 'country_code', 'source'}
    for path in root.rglob('*.csv'):
        with path.open(encoding='utf-8', newline='') as csv_file:
            reader = csv.DictReader(csv_file, delimiter=';')
            if not required.issubset(reader.fieldnames or []):
                continue
            assert 'unique' not in reader.fieldnames
            for row in reader:
                assert None not in row


@pytest.mark.parametrize(
    ('directory', 'category_file'),
    [
        ('.', 'organizationatlas_cat.csv'),
        ('autres', 'list_cat.csv'),
        ('europe/france', 'list_cat.csv'),
    ],
)
def test_category_lists_cover_reference_categories(directory, category_file):
    root = fixtures_root() / directory
    with (root / category_file).open(encoding='utf-8', newline='') as source:
        rows = list(csv.DictReader(source, delimiter=';'))
    categories = {(row['name'], row['country_code']) for row in rows}
    assert len(categories) == len(rows)
    assert all('_' not in row['name'] and row['description'] for row in rows)
    assert all(row['unique'] in {'true', 'false'} for row in rows)
    for path in root.glob('*_ref.csv'):
        with path.open(encoding='utf-8', newline='') as source:
            references = list(csv.DictReader(source, delimiter=';'))
            assert {
                (row['category'], row['country_code']) for row in references
            } <= categories
            assert {
                (row['source_category'], row['country_code'])
                for row in references if row.get('source_category')
            } <= categories


@pytest.mark.django_db
def test_category_library_loads_and_reloads_uniqueness():
    root = fixtures_root()
    paths = [
        root / 'organizationatlas_cat.csv',
        root / 'autres/list_cat.csv',
        root / 'europe/france/list_cat.csv',
    ]
    for path in paths:
        import_csv_file(path)

    for name, country, unique in (
        ('Visual identity', 'XG', False),
        ('API trace', 'XG', False),
        ('Organization relation', 'XG', False),
        ('Stakeholder relation', 'XG', False),
        ('Contractual Sources', 'XG', False),
        ('Decisions', 'FR', False),
        ('APE code', 'FR', True),
        ('Gender', 'XG', True),
    ):
        category = OrganizationAtlasReferenceCategory.objects.get(
            name=name, country_code=country,
        )
        assert category.unique is unique
        category.unique = not unique
        category.save(update_fields=['unique'])

    for path in paths:
        import_csv_file(path)
    assert OrganizationAtlasReferenceCategory.objects.get(
        name='Visual identity', country_code='XG',
    ).unique is False
    assert OrganizationAtlasReferenceCategory.objects.get(
        name='APE code', country_code='FR',
    ).unique is True


@pytest.mark.django_db
@pytest.mark.parametrize(
    ('name', 'country', 'unique'),
    [('ape', 'FR', True), ('visual_identity', '', False)],
)
def test_category_uniqueness_defaults_and_preserves_changes(
    name, country, unique,
):
    category = OrganizationAtlasReferenceCategory.for_name(name, country)
    assert category.unique is unique
    assert category.history.values_list('unique', flat=True).first() is unique

    category.unique = not unique
    category.save(update_fields=['unique'])

    assert (
        OrganizationAtlasReferenceCategory.for_name(name, country).unique
        is not unique
    )
    assert category.history.values_list('unique', flat=True).first() is not unique


@pytest.mark.django_db
def test_category_admin_exposes_uniqueness(client):
    _login_admin(client)
    category = OrganizationAtlasReferenceCategory.objects.get(
        name='Visual identity', country_code='XG',
    )
    url = reverse(
        'admin:django_organizationatlas_organizationatlasreferencecategory_change',
        args=[category.pk],
    )

    response = client.get(url)

    assert response.status_code == 200
    assert 'name="unique"' in response.content.decode()


@pytest.mark.django_db
def test_reference_import_imports_rows(tmp_path):
    csv_path = tmp_path / "reference.csv"
    csv_path.write_text(
        "category;code;description;country_code;source\n"
        "ape;0112Z;Culture du riz;FR;sample\n",
        encoding="utf-8",
    )

    call_command("reference", "--import", str(csv_path))

    reference = OrganizationAtlasReference.objects.get(
        category__name='APE code', category__country_code='FR', code='0112Z',
    )
    assert reference.category.name == "APE code"
    assert reference.category.country_code == "FR"
    assert reference.code == "0112Z"
    assert reference.description == "Culture du riz"
    assert reference.country_code == "FR"
    assert reference.source == "sample"
    assert OrganizationAtlasReferenceCategory.objects.filter(
        name='APE code', country_code='FR',
    ).count() == 1


@pytest.mark.django_db
def test_reference_import_updates_existing_reference(tmp_path):
    category = OrganizationAtlasReferenceCategory.for_name("ape", "FR")
    OrganizationAtlasReference.objects.create(
        category=category,
        code="0112Z",
        description="Old description",
        country_code="FR",
        source="old-source",
    )
    csv_path = tmp_path / "reference.csv"
    csv_path.write_text(
        "category;code;description;country_code;source\n"
        "ape;0112Z;Culture du riz;FR;new-source\n",
        encoding="utf-8",
    )

    call_command("reference", "--import", str(csv_path))

    assert OrganizationAtlasReference.objects.filter(
        category=category, code='0112Z',
    ).count() == 1
    assert OrganizationAtlasReferenceCategory.objects.filter(
        name='APE code', country_code='FR',
    ).count() == 1
    reference = OrganizationAtlasReference.objects.get(
        category=category, code='0112Z',
    )
    assert reference.description == "Culture du riz"
    assert reference.source == "new-source"


@pytest.mark.django_db
def test_reference_import_canonicalizes_existing_data_and_round_trips(tmp_path):
    organization = OrganizationAtlasOrganization.objects.create(
        denomination='Octolo', code='1', source='inpi', country_code='FR',
    )
    data = OrganizationAtlasData.objects.create(
        organization=organization, source='inpi', country_code='FR',
        data_type=OrganizationAtlasDataType.for_key('ape'), value='6201Z',
    )
    csv_path = tmp_path / 'reference.csv'
    csv_path.write_text(
        'category;code;description;country_code;source\n'
        'ape;62.01Z;Programmation;FR;insee\n',
        encoding='utf-8',
    )
    call_command('reference', '--import', str(csv_path))

    reference = OrganizationAtlasReference.objects.get(
        category__name='APE code', category__country_code='FR', code='6201Z',
    )
    data.refresh_from_db()
    assert (reference.code, reference.display_code) == ('6201Z', '62.01Z')
    assert data.value == '62.01Z'

    dump = tmp_path / 'dump.csv'
    call_command('reference', '--export', str(dump))
    call_command('reference', '--import', str(dump))
    reference.refresh_from_db()
    assert reference.display_code == '62.01Z'


@pytest.mark.django_db
@pytest.mark.parametrize('default_value', ['50%', ''])
def test_reference_import_does_not_replace_linked_rule_values(
    tmp_path, default_value,
):
    organization = OrganizationAtlasOrganization.objects.create(
        denomination='Octolo', code='1', source='test', country_code='FR',
    )
    rule = OrganizationAtlasReference.objects.create(
        category=OrganizationAtlasReferenceCategory.for_name('DECISIONS', 'FR'),
        code='ORDINARY_MAJORITY', default_value=default_value, source='test',
    )
    data = OrganizationAtlasData.objects.create(
        organization=organization, source='test', country_code='FR',
        data_type=OrganizationAtlasDataType.for_key('ORDINARY_MAJORITY'),
        value='66%',
    )
    data.reference.add(rule)
    csv_path = tmp_path / 'reference.csv'
    csv_path.write_text(
        'category;code;description;country_code;source\n'
        'ORDINARY_MAJORITY;66.%;other code;FR;test\n',
        encoding='utf-8',
    )

    call_command('reference', '--import', str(csv_path))

    data.refresh_from_db()
    assert data.value == '66%'
    data.save()
    data.refresh_from_db()
    assert data.value == '66%'
    assert organization.rule_value('FR/DECISIONS', 'ordinary_majority') == '66%'


def test_read_csv_requires_expected_columns(tmp_path):
    csv_path = tmp_path / "reference.csv"
    csv_path.write_text("code;description\n0112Z;Culture du riz\n", encoding="utf-8")

    with pytest.raises(CommandError):
        read_csv(csv_path)


@pytest.mark.parametrize(
    ('filename', 'content'),
    [
        ('wrong_ref.csv', 'name;description;country_code\nape;APE;FR\n'),
        (
            'wrong_cat.csv',
            'category;code;description;country_code;source\n'
            'ape;0112Z;Example;FR;test\n',
        ),
    ],
)
def test_library_import_uses_suffix_not_headers(
    tmp_path, monkeypatch, filename, content,
):
    monkeypatch.setattr(
        'django_organizationatlas.services.reference.fixtures_root',
        lambda: tmp_path,
    )
    path = tmp_path / filename
    path.write_text(content, encoding='utf-8')

    with pytest.raises(CommandError, match='Missing required CSV columns'):
        import_csv_file(path)


@pytest.mark.django_db
def test_external_csv_import_keeps_header_detection(tmp_path):
    path = tmp_path / 'external_cat.csv'
    path.write_text(
        'category;code;description;country_code;source\n'
        'ape;0112Z;Example;FR;test\n',
        encoding='utf-8',
    )

    import_csv_file(path)

    assert OrganizationAtlasReference.objects.filter(
        category__name='APE code', code='0112Z',
    ).exists()


@pytest.mark.django_db
def test_reference_export_exports_dump_csv(tmp_path):
    OrganizationAtlasReference.objects.create(
        category=OrganizationAtlasReferenceCategory.for_name("ape", "FR"),
        code="0112Z",
        description="Culture du riz",
        country_code="FR",
        source="sample",
    )
    dump_dir = tmp_path / "reference" / "export"

    call_command("reference", "--export", str(dump_dir))

    dump_path = dump_dir / "dump.csv"
    assert dump_path.exists()
    with dump_path.open(encoding='utf-8', newline='') as csv_file:
        rows = list(csv.DictReader(csv_file, delimiter=';'))
    assert {
        'category': 'APE code',
        'code': '0112Z',
        'description': 'Culture du riz',
        'country_code': 'FR',
        'source': 'sample',
        'display_code': '0112Z',
        'default_value': '',
    } in rows


def _login_admin(client):
    get_user_model().objects.create_superuser(
        username="admin",
        email="admin@example.com",
        password="admin",
    )
    client.force_login(get_user_model().objects.get(username="admin"))


@pytest.mark.django_db
def test_admin_import_reference_uploads_csv(client):
    _login_admin(client)
    csv_file = SimpleUploadedFile(
        "reference.csv",
        b"category;code;description;country_code;source\n"
        b"ape;0112Z;Culture du riz;FR;sample\n",
        content_type="text/csv",
    )
    url = reverse("admin:django_organizationatlas_organizationatlasreference_import_from_csv")

    response = client.post(url, {"csv_file": csv_file, "_save": "Save"})

    assert response.status_code == 302
    assert response.url == reverse(
        "admin:django_organizationatlas_organizationatlasreference_changelist"
    )
    assert OrganizationAtlasReference.objects.filter(
        category__name="APE code",
        category__country_code="FR",
        code="0112Z",
        description="Culture du riz",
        source="sample",
    ).exists()


@pytest.mark.django_db
def test_default_fixture_is_loaded_by_the_initial_migration():
    source = OrganizationAtlasReference.objects.get(category__name="API trace", code="SOURCE")
    assert source.display_code == "source"
    assert source.description == "Current response returned by the provider"
    history = OrganizationAtlasReference.objects.get(category__name="API trace", code="HISTORY")
    assert history.display_code == "history"
    assert history.description == "History returned by the provider"

    created_count, updated_count = load_default_references()
    assert created_count == 0
    assert updated_count == 7
    assert OrganizationAtlasReference.objects.filter(category__name="API trace").count() == 2


@pytest.mark.django_db
def test_reference_import_loads_french_files():
    call_command("reference", "--import")

    assert OrganizationAtlasReference.objects.filter(
        category__name="APE code",
        category__country_code="FR",
    ).count() == 732
    assert OrganizationAtlasReference.objects.filter(
        category__name="Legal form",
        category__country_code="FR",
    ).count() == 309
    ape = OrganizationAtlasReferenceCategory.objects.with_reference_count().get(name="APE code", country_code="FR")
    assert ape.sql_reference_count == 732
    assert OrganizationAtlasReferenceCategory.objects.filter(name="Legal form", country_code="FR").exists()
    gender = OrganizationAtlasReference.objects.get(category__name="Gender", code="MALE")
    assert gender.display_code == "male"
    assert gender.description == "Male person"
    assert gender.priority == 10
    assert gender.source == "organizationatlas"
    assert gender.country_code == "XG"
    assert str(gender.category) == "XG/Gender"
    assert gender.source_label() == "XG/organizationatlas"


@pytest.mark.django_db
def test_library_lists_fixture_tree(client):
    _login_admin(client)
    url = reverse("admin:django_organizationatlas_organizationatlasreference_import_from_library")

    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()
    assert content.index("column-name") < content.index("column-directory")
    assert 'name="_selected_action"' in content
    assert "europe/france" in content
    assert "ape_ref.csv" in content
    assert "legalform_ref.csv" in content
    assert "list_cat.csv" not in content
    assert "fixture=europe/france/ape_ref.csv" in content

    searched = client.get(url, {"q": "ape"})
    searched_html = searched.content.decode()
    assert searched.status_code == 200
    assert "ape_ref.csv" in searched_html
    assert "legalform_ref.csv" not in searched_html

    by_directory = client.get(url, {"directory": "europe/france"})
    directory_html = by_directory.content.decode()
    assert by_directory.status_code == 200
    assert "ape_ref.csv" in directory_html
    assert "gender_ref.csv" not in directory_html


@pytest.mark.django_db
def test_library_action_loads_selected_fixtures(client):
    _login_admin(client)
    url = reverse("admin:django_organizationatlas_organizationatlasreference_import_from_library")

    loaded = client.post(
        url,
        {
            "action": "load_fixtures",
            "index": "0",
            "_selected_action": [
                "autres/gender_ref.csv",
                "europe/france/company_rules_ref.csv",
            ],
        },
    )

    assert loaded.status_code == 302
    assert loaded.url == reverse(
        "admin:django_organizationatlas_organizationatlasreference_changelist"
    )
    assert OrganizationAtlasReference.objects.filter(category__name="Gender", code="MALE").exists()
    assert OrganizationAtlasReference.objects.filter(code="ORDINARY_MAJORITY").exists()


@pytest.mark.django_db
def test_library_confirm_loads_and_reloads_fixture(client):
    _login_admin(client)
    url = reverse("admin:django_organizationatlas_organizationatlasreference_import_library_file")
    fixture = url + "?fixture=europe/france/legalform_ref.csv"

    confirm = client.get(fixture)
    assert confirm.status_code == 200
    assert "Load or reload europe/france/legalform_ref.csv?" in confirm.content.decode()

    created = client.post(fixture, {"action": "confirm"})
    assert created.status_code == 302
    assert OrganizationAtlasReference.objects.filter(category__name="Legal form").count() == 309

    reloaded = client.post(fixture, {"action": "confirm"})
    assert reloaded.status_code == 302
    assert OrganizationAtlasReference.objects.filter(category__name="Legal form").count() == 309
    assert OrganizationAtlasReferenceCategory.objects.filter(name="Legal form", country_code="FR").count() == 1


@pytest.mark.django_db
def test_category_library_lists_and_loads_only_categories(client):
    _login_admin(client)
    list_url = reverse(
        'admin:django_organizationatlas_'
        'organizationatlasreferencecategory_import_from_library',
    )
    confirm_url = reverse(
        'admin:django_organizationatlas_'
        'organizationatlasreferencecategory_import_library_file',
    )
    reference_count = OrganizationAtlasReference.objects.count()

    page = client.get(list_url)
    content = page.content.decode()
    assert page.status_code == 200
    assert 'fixture=europe/france/list_cat.csv' in content
    assert 'fixture=autres/list_cat.csv' in content
    assert 'fixture=organizationatlas_cat.csv' in content
    assert 'ape_ref.csv' not in content
    target = f'{confirm_url}?fixture=europe/france/list_cat.csv'
    assert client.get(target).status_code == 200
    assert client.post(target, {'action': 'confirm'}).status_code == 302
    assert OrganizationAtlasReferenceCategory.objects.filter(
        name='Decisions', country_code='FR',
        description='Rules governing company decisions.',
    ).exists()

    response = client.post(list_url, {
        'action': 'load_fixtures',
        'index': '0',
        '_selected_action': ['autres/list_cat.csv'],
    })
    assert response.status_code == 302
    assert response.url == reverse(
        'admin:django_organizationatlas_organizationatlasreferencecategory_changelist',
    )
    assert OrganizationAtlasReferenceCategory.objects.filter(name='Gender').exists()
    assert OrganizationAtlasReference.objects.count() == reference_count


@pytest.mark.django_db
@pytest.mark.parametrize(
    ('model', 'fixture'),
    [
        ('organizationatlasreference', 'europe/france/list_cat.csv'),
        ('organizationatlasreferencecategory', 'europe/france/ape_ref.csv'),
    ],
)
def test_library_rejects_other_fixture_type(client, model, fixture):
    _login_admin(client)
    url = reverse(f'admin:django_organizationatlas_{model}_import_library_file')
    before = (
        OrganizationAtlasReference.objects.count(),
        OrganizationAtlasReferenceCategory.objects.count(),
    )

    response = client.post(f'{url}?fixture={fixture}', {'action': 'confirm'})

    assert response.status_code == 302
    assert (
        OrganizationAtlasReference.objects.count(),
        OrganizationAtlasReferenceCategory.objects.count(),
    ) == before


@pytest.mark.django_db
def test_category_library_requires_only_category_permission(client):
    user = get_user_model().objects.create_user('category-editor', is_staff=True)
    user.user_permissions.add(Permission.objects.get(
        content_type__app_label='django_organizationatlas',
        codename='change_organizationatlasreferencecategory',
    ))
    client.force_login(user)
    category_url = reverse(
        'admin:django_organizationatlas_'
        'organizationatlasreferencecategory_import_from_library',
    )
    reference_url = reverse(
        'admin:django_organizationatlas_'
        'organizationatlasreference_import_from_library',
    )

    assert client.get(category_url).status_code == 200
    assert client.get(reference_url).status_code == 403


@pytest.mark.django_db
def test_reference_library_does_not_grant_category_import(client):
    user = get_user_model().objects.create_user('reference-editor', is_staff=True)
    user.user_permissions.add(Permission.objects.get(
        content_type__app_label='django_organizationatlas',
        codename='change_organizationatlasreference',
    ))
    client.force_login(user)
    reference_url = reverse(
        'admin:django_organizationatlas_'
        'organizationatlasreference_import_from_library',
    )
    category_url = reverse(
        'admin:django_organizationatlas_'
        'organizationatlasreferencecategory_import_from_library',
    )

    assert client.get(reference_url).status_code == 200
    assert client.get(category_url).status_code == 403


@pytest.mark.django_db
def test_category_import_preserves_description_for_blank_cells(tmp_path):
    category = OrganizationAtlasReferenceCategory.objects.create(
        name='APE code', country_code='FR', description='Existing description',
    )
    path = tmp_path / 'categories.csv'
    path.write_text(
        'name;description;country_code\nAPE code;;FR\n', encoding='utf-8',
    )

    call_command('reference', '--import', str(path))

    category.refresh_from_db()
    assert category.description == 'Existing description'


@pytest.mark.django_db
def test_category_import_uses_and_preserves_visual_identity_default():
    rows = [{
        'name': 'visual_identity',
        'country_code': 'FR',
        'description': '',
    }]
    import_category_rows(rows)
    category = OrganizationAtlasReferenceCategory.objects.get(
        name='Visual identity', country_code='FR',
    )
    assert category.unique is False

    category.unique = True
    category.save(update_fields=['unique'])
    import_category_rows(rows)
    category.refresh_from_db()
    assert category.unique is True


@pytest.mark.django_db
def test_category_csv_import_updates_uniqueness_and_preserves_blank(tmp_path):
    path = tmp_path / 'categories.csv'
    path.write_text(
        'name;description;country_code;unique\n'
        'Sample;;FR;false\nOther sample;;FR;TRUE\n',
        encoding='utf-8',
    )
    import_csv_file(path)
    first = OrganizationAtlasReferenceCategory.objects.get(name='Sample')
    second = OrganizationAtlasReferenceCategory.objects.get(name='Other sample')
    assert first.unique is False
    assert second.unique is True

    path.write_text(
        'name;description;country_code;unique\n'
        'Sample;;FR;true\nOther sample;;FR;\n',
        encoding='utf-8',
    )
    import_csv_file(path)
    first.refresh_from_db()
    second.refresh_from_db()
    assert first.unique is True
    assert second.unique is True


@pytest.mark.django_db
def test_category_csv_without_unique_preserves_existing_value(tmp_path):
    category = OrganizationAtlasReferenceCategory.objects.create(
        name='Custom', country_code='FR', unique=False,
    )
    path = tmp_path / 'categories.csv'
    path.write_text(
        'name;country_code\nCustom;FR\nNew category;FR\n', encoding='utf-8',
    )

    import_csv_file(path)

    category.refresh_from_db()
    assert category.unique is False
    assert OrganizationAtlasReferenceCategory.objects.get(
        name='New category',
    ).unique is True


def test_category_csv_rejects_invalid_uniqueness(tmp_path):
    path = tmp_path / 'categories.csv'
    path.write_text(
        'name;country_code;unique\nCustom;FR;yes\n', encoding='utf-8',
    )

    with pytest.raises(CommandError, match='true or false'):
        import_csv_file(path)


@pytest.mark.django_db
def test_company_rule_fixtures_load_and_reload():
    base = fixtures_root() / "europe" / "france"
    call_command("reference", "--import", str(base / "list_cat.csv"))
    call_command("reference", "--import", str(base / "company_rules_ref.csv"))

    decisions = OrganizationAtlasReferenceCategory.objects.get(name="Decisions", country_code="FR")
    assert decisions.description == 'Rules governing company decisions.'
    law = OrganizationAtlasReferenceCategory.objects.get(name="Law", country_code="FR")
    assert law.description == 'Applicable laws and regulations.'
    ordinary = OrganizationAtlasReference.objects.get(category=decisions, code="ORDINARY_MAJORITY")
    assert ordinary.default_value == "50%"
    assert ordinary.source_category_id is None
    extraordinary = OrganizationAtlasReference.objects.get(
        category=decisions,
        code="EXTRAORDINARY_MAJORITY",
    )
    assert extraordinary.default_value == "50%"
    quorum = OrganizationAtlasReference.objects.get(category=decisions, code="QUORUM")
    assert quorum.default_value == "to complete"
    assert quorum.description == "Quorum"
    assert OrganizationAtlasReference.objects.get(code="VOTING_RIGHTS").category.name == "Statutes"
    assert OrganizationAtlasReference.objects.filter(
        category__name__in=["Legal", "Statutes", "Governance", "Decisions", "Contracts"],
    ).count() == 23

    call_command("reference", "--import", str(base / "list_cat.csv"))
    call_command("reference", "--import", str(base / "company_rules_ref.csv"))

    assert OrganizationAtlasReference.objects.filter(code="ORDINARY_MAJORITY").count() == 1
    assert OrganizationAtlasReferenceCategory.objects.filter(name="Law", country_code="FR").count() == 1


@pytest.mark.django_db
def test_library_confirm_rejects_paths_outside_fixtures(client):
    _login_admin(client)
    url = reverse("admin:django_organizationatlas_organizationatlasreference_import_library_file")

    before = OrganizationAtlasReference.objects.count()
    response = client.post(url + "?fixture=../../secret.csv", {"action": "confirm"})

    assert response.status_code == 302
    assert OrganizationAtlasReference.objects.count() == before
