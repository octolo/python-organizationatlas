import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.urls import reverse

from django_organizationatlas.managers.reference import FEATURE_CATEGORY
from django_organizationatlas.models import (
    OrganizationAtlasFeatureManager,
    OrganizationAtlasOrganization,
    OrganizationAtlasReference,
    OrganizationAtlasReferenceCategory,
)


def _reference(category_name, code):
    category = OrganizationAtlasReferenceCategory.for_name(category_name, "")
    return OrganizationAtlasReference.objects.create(
        category=category,
        code=code,
        description=code,
        source="organizationatlas",
    )


@pytest.mark.django_db
def test_features_queryset_returns_references_tagged_feature():
    feature = _reference(FEATURE_CATEGORY, "meetings")
    _reference("ape", "62.01Z")

    assert list(OrganizationAtlasReference.objects.features().values_list("code", flat=True)) == [
        feature.code
    ]


@pytest.mark.django_db
def test_feature_manager_rejects_a_reference_that_is_not_a_feature():
    organization = OrganizationAtlasOrganization.objects.create(
        denomination="Octolo",
        code="917432254",
        source="organizationatlas",
        country_code="FR",
    )
    ape = _reference("ape", "62.01Z")
    feature_manager = OrganizationAtlasFeatureManager(
        organization=organization,
        feature=ape,
        role=OrganizationAtlasFeatureManager.Role.USER,
    )

    with pytest.raises(ValidationError) as raised:
        feature_manager.clean()

    assert "feature" in raised.value.error_dict


@pytest.mark.django_db
def test_load_features_button_creates_and_updates_references_from_settings(client, settings):
    get_user_model().objects.create_superuser("admin", "admin@example.com", "admin")
    client.force_login(get_user_model().objects.get(username="admin"))
    settings.ORGANIZATIONATLAS_FEATURES = [
        {"code": "meetings", "description": "Meetings"},
        "capitalisation",
    ]
    url = reverse("admin:django_organizationatlas_organizationatlasfeaturemanager_load_features")
    changelist = reverse(
        "admin:django_organizationatlas_organizationatlasfeaturemanager_changelist"
    )

    listing = client.get(changelist)
    assert listing.status_code == 200
    assert "Load features" in listing.content.decode()
    assert url in listing.content.decode()

    confirm = client.get(url)
    assert confirm.status_code == 200
    assert "Load or update features from settings: meetings, capitalisation?" in confirm.content.decode()

    created = client.post(url, {"action": "confirm"})
    assert created.status_code == 302
    reference_changelist = reverse(
        "admin:django_organizationatlas_organizationatlasreference_changelist"
    )
    feature_category = OrganizationAtlasReferenceCategory.objects.get(name="feature")
    assert created.url == f"{reference_changelist}?category__id__exact={feature_category.pk}"
    _reference("ape", "62.01Z")
    filtered = client.get(created.url)
    assert filtered.status_code == 200
    filtered_html = filtered.content.decode()
    assert "Meetings" in filtered_html
    assert "62.01Z" not in filtered_html
    meetings = OrganizationAtlasReference.objects.get(category__name="feature", code="MEETINGS")
    assert meetings.description == "Meetings"
    assert meetings.source == "settings"
    capitalisation = OrganizationAtlasReference.objects.get(category__name="feature", code="CAPITALISATION")
    assert capitalisation.description == ""

    settings.ORGANIZATIONATLAS_FEATURES = [
        {"code": "meetings", "description": "General meetings"},
    ]
    updated = client.post(url, {"action": "confirm"})
    assert updated.status_code == 302
    assert updated.url == f"{reference_changelist}?category__id__exact={feature_category.pk}"
    meetings.refresh_from_db()
    assert meetings.description == "General meetings"
    assert OrganizationAtlasReference.objects.filter(category__name="feature").count() == 2


@pytest.mark.django_db
def test_load_features_button_warns_when_the_setting_is_empty(client, settings):
    get_user_model().objects.create_superuser("admin", "admin@example.com", "admin")
    client.force_login(get_user_model().objects.get(username="admin"))
    settings.ORGANIZATIONATLAS_FEATURES = []
    url = reverse("admin:django_organizationatlas_organizationatlasfeaturemanager_load_features")

    response = client.get(url, follow=True)

    assert response.status_code == 200
    assert "No features are configured in ORGANIZATIONATLAS_FEATURES." in response.content.decode()
    assert not OrganizationAtlasReference.objects.filter(category__name="feature").exists()


@pytest.mark.django_db
def test_organization_change_shows_its_features(client):
    get_user_model().objects.create_superuser("admin", "admin@example.com", "admin")
    client.force_login(get_user_model().objects.get(username="admin"))
    organization = OrganizationAtlasOrganization.objects.create(
        denomination="Octolo",
        code="917432254",
        source="organizationatlas",
        country_code="FR",
    )
    category = OrganizationAtlasReferenceCategory.for_name(FEATURE_CATEGORY, "")
    feature = OrganizationAtlasReference.objects.create(
        category=category,
        code="meetings",
        description="Meetings",
        source="settings",
    )
    OrganizationAtlasFeatureManager.objects.create(
        organization=organization,
        feature=feature,
        role=OrganizationAtlasFeatureManager.Role.ADMIN,
    )
    url = reverse(
        "admin:django_organizationatlas_organizationatlasorganization_change",
        args=[organization.pk],
    )

    html = client.get(url).content.decode()

    assert "feature_managers-group" in html
    assert "meetings" in html


def test_contributor_can_edit_and_stops_before_export():
    manager = OrganizationAtlasFeatureManager(level=OrganizationAtlasFeatureManager.Level.CONTRIBUTOR)

    assert manager.can_read
    assert manager.can_view
    assert manager.can_contribute
    assert not manager.involved_only
    assert not manager.can_export
    assert not manager.can_manage


def test_involved_level_reads_only_its_own_data():
    manager = OrganizationAtlasFeatureManager(level=OrganizationAtlasFeatureManager.Level.INVOLVED)

    assert manager.can_read
    assert manager.involved_only
    assert not manager.can_view
    assert not manager.can_contribute


def test_viewer_reads_all_data_without_editing():
    manager = OrganizationAtlasFeatureManager(level=OrganizationAtlasFeatureManager.Level.VIEWER)

    assert manager.can_read
    assert manager.can_view
    assert not manager.involved_only
    assert not manager.can_contribute


def test_exporter_includes_edit_and_stops_before_management():
    manager = OrganizationAtlasFeatureManager(level=OrganizationAtlasFeatureManager.Level.EXPORTER)

    assert manager.can_contribute
    assert manager.can_export
    assert not manager.can_manage


def test_manager_level_includes_every_lower_level():
    manager = OrganizationAtlasFeatureManager(level=OrganizationAtlasFeatureManager.Level.MANAGER)

    assert manager.can_read
    assert manager.can_view
    assert manager.can_contribute
    assert manager.can_export
    assert manager.can_manage


def test_disabled_feature_grants_no_level():
    manager = OrganizationAtlasFeatureManager(
        level=OrganizationAtlasFeatureManager.Level.MANAGER,
        enabled=False,
    )

    assert not manager.has_level(OrganizationAtlasFeatureManager.Level.INVOLVED)
    assert not manager.can_manage


def test_feature_field_uses_the_feature_category():
    field = OrganizationAtlasFeatureManager._meta.get_field("feature")

    assert field.get_limit_choices_to() == {"category__name": FEATURE_CATEGORY}
    assert "unique_organization_feature_role" in {
        constraint.name for constraint in OrganizationAtlasFeatureManager._meta.constraints
    }
