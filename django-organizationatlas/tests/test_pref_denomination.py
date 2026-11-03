from namedid.generators import generate_namedid

from django_organizationatlas.models import OrganizationAtlasOrganization


def test_pref_denomination_prefers_short_name():
    organization = OrganizationAtlasOrganization(
        denomination="Octolo SAS",
        short_denomination="Octolo",
        code="917432254",
    )
    assert organization.pref_denomination == "Octolo"


def test_pref_denomination_falls_back_to_denomination():
    organization = OrganizationAtlasOrganization(
        denomination="Octolo SAS",
        short_denomination="",
        code="917432254",
    )
    assert organization.pref_denomination == "Octolo SAS"

    organization.short_denomination = None
    assert organization.pref_denomination == "Octolo SAS"


def test_named_id_uses_pref_denomination():
    field = OrganizationAtlasOrganization._meta.get_field("named_id")
    organization = OrganizationAtlasOrganization(
        denomination="Octolo SAS",
        short_denomination="Octolo",
        code="917432254",
    )
    base = generate_namedid(organization, field.source_fields, field.separator)
    assert base == "octolo-917432254"

    organization.short_denomination = None
    base = generate_namedid(organization, field.source_fields, field.separator)
    assert base == "octolo-sas-917432254"


def test_truncate_denomination_uses_the_short_name_when_set():
    organization = OrganizationAtlasOrganization(
        denomination="D" * 50,
        short_denomination="S" * 50,
        code="917432254",
    )
    assert organization.pref_denomination == "S" * 50
    assert organization.truncate_denomination == "S" * 30


def test_truncate_denomination_leaves_room_for_the_code():
    organization = OrganizationAtlasOrganization(
        denomination="A" * 50,
        short_denomination="",
        code="917432254",
    )
    assert organization.truncate_denomination == "A" * 30
    field = OrganizationAtlasOrganization._meta.get_field("named_id")
    base = generate_namedid(organization, field.source_fields, field.separator)
    assert base == ("a" * 30) + "-917432254"
    assert len(base) == field.max_length
