import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.urls import reverse

from django_organizationatlas.models import (
    OrganizationAtlasReference,
    OrganizationAtlasReferenceCategory,
)
from django_organizationatlas.services.reference import read_csv


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


@pytest.mark.django_db
def test_reference_import_imports_rows(tmp_path):
    csv_path = tmp_path / "reference.csv"
    csv_path.write_text(
        "category;code;description;country_code;source\n"
        "ape;0112Z;Culture du riz;FR;sample\n",
        encoding="utf-8",
    )

    call_command("reference", "--import", str(csv_path))

    reference = OrganizationAtlasReference.objects.get()
    assert reference.category.name == "ape"
    assert reference.category.country_code == "FR"
    assert reference.code == "0112Z"
    assert reference.description == "Culture du riz"
    assert reference.country_code == "FR"
    assert reference.source == "sample"
    assert OrganizationAtlasReferenceCategory.objects.count() == 1


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

    assert OrganizationAtlasReference.objects.count() == 1
    assert OrganizationAtlasReferenceCategory.objects.count() == 1
    reference = OrganizationAtlasReference.objects.get()
    assert reference.description == "Culture du riz"
    assert reference.source == "new-source"


def test_read_csv_requires_expected_columns(tmp_path):
    csv_path = tmp_path / "reference.csv"
    csv_path.write_text("code;description\n0112Z;Culture du riz\n", encoding="utf-8")

    with pytest.raises(CommandError):
        read_csv(csv_path)


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
    assert dump_path.read_text(encoding="utf-8") == (
        "category;code;description;country_code;source\n"
        "ape;0112Z;Culture du riz;FR;sample\n"
    )


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
        category__name="ape",
        category__country_code="FR",
        code="0112Z",
        description="Culture du riz",
        source="sample",
    ).exists()


@pytest.mark.django_db
def test_reference_import_loads_french_files():
    call_command("reference", "--import")

    assert OrganizationAtlasReference.objects.filter(
        category__name="ape",
        category__country_code="FR",
    ).count() == 732
    assert OrganizationAtlasReference.objects.filter(
        category__name="legalform",
        category__country_code="FR",
    ).count() == 309
    assert OrganizationAtlasReferenceCategory.objects.filter(name="ape", country_code="FR").exists()
    assert OrganizationAtlasReferenceCategory.objects.filter(name="legalform", country_code="FR").exists()


@pytest.mark.django_db
def test_library_lists_fixture_tree(client):
    _login_admin(client)
    url = reverse("admin:django_organizationatlas_organizationatlasreference_import_from_library")

    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()
    assert "europe/france" in content
    assert "ape.csv" in content
    assert "legalform.csv" in content
    assert "fixture=europe/france/ape.csv" in content


@pytest.mark.django_db
def test_library_confirm_loads_and_reloads_fixture(client):
    _login_admin(client)
    url = reverse("admin:django_organizationatlas_organizationatlasreference_import_library_file")
    fixture = url + "?fixture=europe/france/legalform.csv"

    confirm = client.get(fixture)
    assert confirm.status_code == 200
    assert "Load or reload europe/france/legalform.csv?" in confirm.content.decode()

    created = client.post(fixture, {"action": "confirm"})
    assert created.status_code == 302
    assert OrganizationAtlasReference.objects.filter(category__name="legalform").count() == 309

    reloaded = client.post(fixture, {"action": "confirm"})
    assert reloaded.status_code == 302
    assert OrganizationAtlasReference.objects.filter(category__name="legalform").count() == 309
    assert OrganizationAtlasReferenceCategory.objects.filter(name="legalform", country_code="FR").count() == 1


@pytest.mark.django_db
def test_library_confirm_rejects_paths_outside_fixtures(client):
    _login_admin(client)
    url = reverse("admin:django_organizationatlas_organizationatlasreference_import_library_file")

    response = client.post(url + "?fixture=../../secret.csv", {"action": "confirm"})

    assert response.status_code == 302
    assert OrganizationAtlasReference.objects.count() == 0
