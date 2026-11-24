import pytest

from django_organizationatlas.models.organization import (
    OrganizationAtlasOrganization,
    organization_abbreviation,
)


def test_abbreviation_keeps_the_first_letter_of_words_of_at_least_two_letters():
    assert organization_abbreviation("Société Générale") == "SG"
    assert organization_abbreviation("octolo sas") == "OS"
    assert organization_abbreviation("La Banque Postale") == "LBP"
    assert organization_abbreviation("L'Oréal") == "L"
    assert organization_abbreviation("Jean-Pierre Dupont") == "JD"
    assert organization_abbreviation("A BC") == "B"
    assert organization_abbreviation("") == ""


@pytest.mark.django_db
def test_abbreviation_is_generated_when_empty_and_kept_when_set():
    generated = OrganizationAtlasOrganization.objects.create(
        denomination="Société Générale",
        code="1",
        source="insee",
        country_code="FR",
    )
    assert generated.abbreviation == "SG"

    custom = OrganizationAtlasOrganization.objects.create(
        denomination="Société Générale",
        abbreviation="socgen",
        code="2",
        source="insee",
        country_code="FR",
    )
    assert custom.abbreviation == "SOCGEN"

    custom.denomination = "Banque Générale"
    custom.save()
    assert custom.abbreviation == "SOCGEN"

    custom.abbreviation = "bgen"
    custom.save(update_fields=["abbreviation"])
    custom.refresh_from_db()
    assert custom.abbreviation == "BGEN"

    custom.abbreviation = ""
    custom.save()
    assert custom.abbreviation == "BG"
