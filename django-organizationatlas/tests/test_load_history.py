from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth.models import Permission
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError, transaction
from django.test import Client
from django.urls import reverse

from django_organizationatlas.forms.organization import history_provider_choices
from django_organizationatlas.helpers import (
    OrganizationHistoryError,
    apply_organization_history,
    fetch_organization_history,
    load_organization_history,
)
from django_organizationatlas.models import (
    OrganizationAtlasData,
    OrganizationAtlasDataType,
    OrganizationAtlasOrganization,
    OrganizationAtlasOrganizationRelation,
    OrganizationAtlasStakeholderRelation,
)


def _organization():
    return OrganizationAtlasOrganization.objects.create(
        denomination="Octolo",
        code="917432254",
        source="insee",
        country_code="FR",
    )


def _client():
    user = User.objects.create_superuser("ada", "ada@example.com", "password")
    client = Client()
    client.force_login(user)
    return client


def _view_only_client():
    user = User.objects.create_user(
        "viewer",
        "viewer@example.com",
        "password",
        is_staff=True,
    )
    user.user_permissions.add(
        Permission.objects.get(
            content_type__app_label="django_organizationatlas",
            codename="view_organizationatlasorganization",
        )
    )
    client = Client()
    client.force_login(user)
    return client


def _url(name, organization):
    return reverse(
        f"admin:django_organizationatlas_organizationatlasorganization_{name}",
        args=[organization.pk],
    )


_ROWS = [
    {
        "field": "denomination",
        "value": "OLD",
        "valid_from": "2010-01-01",
        "valid_to": "2019-12-31",
        "country_code": "FR",
        "backend": "insee",
    },
    {
        "field": "denomination",
        "value": "NEW",
        "valid_from": "2020-01-01",
        "valid_to": None,
        "country_code": "FR",
        "backend": "insee",
    },
    {
        "field": "ape",
        "value": "62.01Z",
        "valid_from": "2015-06-01",
        "valid_to": None,
        "country_code": "FR",
        "backend": "insee",
    },
]


@pytest.mark.django_db
def test_history_provider_choices_keep_providers_that_implement_the_service():
    names = {value for value, _label in history_provider_choices()}
    assert names == {"insee"}


@pytest.mark.django_db
def test_load_history_button_opens_provider_form():
    organization = _organization()
    client = _client()

    change = client.get(_url("change", organization))
    assert change.status_code == 200
    change_html = change.content.decode()
    assert "Load history" in change_html
    assert _url("load_history", organization) in change_html

    form_page = client.get(_url("load_history", organization))
    assert form_page.status_code == 200
    html = form_page.content.decode()
    assert "<select" in html
    assert 'value="insee"' in html
    assert 'value="huwise"' not in html
    assert 'value="inpi"' not in html
    assert 'value="entdatagouv"' not in html


@pytest.mark.django_db
@pytest.mark.parametrize("method", ["get", "post"])
def test_view_only_user_cannot_load_history(method):
    organization = _organization()
    client = _view_only_client()

    with patch(
        "django_organizationatlas.admin.organization.load_organization_history"
    ) as load:
        response = getattr(client, method)(
            _url("load_history", organization),
            {"provider": "insee"} if method == "post" else None,
        )

    assert response.status_code == 403
    load.assert_not_called()


@pytest.mark.django_db
@pytest.mark.parametrize("method", ["get", "post"])
def test_view_only_user_cannot_refresh_organization(method):
    organization = _organization()
    client = _view_only_client()

    with patch(
        "django_organizationatlas.admin.organization.fetch_organization_for_refresh"
    ) as fetch:
        response = getattr(client, method)(
            _url("refresh", organization),
            {"provider": "insee"} if method == "post" else None,
        )

    assert response.status_code == 403
    fetch.assert_not_called()


@pytest.mark.django_db
def test_apply_organization_history_stores_periods_once():
    organization = _organization()
    OrganizationAtlasData.objects.create(
        organization=organization,
        source="insee",
        country_code="FR",
        data_type=OrganizationAtlasDataType.for_key("denomination"),
        value="CURRENT",
    )

    assert apply_organization_history(organization, _ROWS, source="insee") == 3
    assert apply_organization_history(organization, _ROWS, source="insee") == 3
    assert organization.to_organizationatlasdata.count() == 3

    denominations = organization.to_organizationatlasdata.filter(
        data_type__data_type="denomination",
    ).order_by("valid_from")
    assert [(row.value, row.valid_from, row.valid_to) for row in denominations] == [
        ("OLD", date(2010, 1, 1), date(2019, 12, 31)),
        ("NEW", date(2020, 1, 1), None),
    ]
    assert organization.to_organizationatlasdata.filter(valid_to__isnull=True).count() == 2


@pytest.mark.django_db
def test_load_organization_history_stores_apihistorytrace():
    organization = _organization()

    with patch(
        "django_organizationatlas.helpers.fetch_organization_history",
        return_value=_ROWS,
    ):
        assert load_organization_history(organization, "insee") == 3
        assert load_organization_history(organization, "insee") == 3

    traces = organization.to_organizationatlasdata.filter(data_type__data_type="apihistorytrace")
    assert traces.count() == 1
    trace = traces.get()
    assert trace.data_type.value_type == "json"
    assert trace.valid_to is None
    assert "OLD" in trace.value
    assert "62.01Z" in trace.value


@pytest.mark.django_db
def test_load_organization_history_rolls_back_trace_when_apply_fails():
    organization = _organization()

    with (
        patch(
            "django_organizationatlas.helpers.fetch_organization_history",
            return_value=_ROWS,
        ),
        patch(
            "django_organizationatlas.helpers.apply_organization_history",
            side_effect=OrganizationHistoryError("invalid row"),
        ),
        pytest.raises(OrganizationHistoryError, match="invalid row"),
    ):
        load_organization_history(organization, "insee")

    assert not organization.to_organizationatlasdata.filter(
        data_type__data_type="apihistorytrace"
    ).exists()


@pytest.mark.django_db
def test_apply_history_closes_previous_open_period():
    organization = _organization()
    datatype = OrganizationAtlasDataType.for_key("denomination")
    previous = OrganizationAtlasData.objects.create(
        organization=organization,
        source="insee",
        country_code="FR",
        data_type=datatype,
        value="OLD",
        valid_from=date(2020, 1, 1),
    )

    apply_organization_history(
        organization,
        [
            {
                "field": "denomination",
                "value": "NEW",
                "valid_from": "2021-01-01",
                "valid_to": None,
                "country_code": "FR",
            }
        ],
        source="insee",
    )

    previous.refresh_from_db()
    assert previous.valid_to == date(2020, 12, 31)
    assert organization.to_organizationatlasdata.get(
        data_type=datatype,
        valid_to__isnull=True,
    ).value == "NEW"


@pytest.mark.django_db
def test_closed_periods_are_matched_on_both_bounds():
    organization = _organization()
    rows = [
        {
            "field": "denomination",
            "value": "FIRST",
            "valid_from": "2020-01-01",
            "valid_to": "2020-06-30",
            "country_code": "FR",
        },
        {
            "field": "denomination",
            "value": "SECOND",
            "valid_from": "2020-01-01",
            "valid_to": "2020-12-31",
            "country_code": "FR",
        },
    ]

    apply_organization_history(organization, rows, source="insee")

    periods = organization.to_organizationatlasdata.order_by("valid_to")
    assert [(row.value, row.valid_to) for row in periods] == [
        ("FIRST", date(2020, 6, 30)),
        ("SECOND", date(2020, 12, 31)),
    ]


@pytest.mark.django_db
def test_invalid_history_date_has_structured_error():
    organization = _organization()

    with pytest.raises(
        OrganizationHistoryError,
        match="Invalid valid_from date",
    ):
        apply_organization_history(
            organization,
            [{"field": "denomination", "value": "NEW", "valid_from": "invalid"}],
            source="insee",
        )


def test_partial_provider_error_is_not_silenced():
    provider = MagicMock()
    provider.get_service_normalize.return_value = [{"field": "denomination", "value": "NEW"}]

    with (
        patch(
            "django_organizationatlas.helpers.get_organization_history",
            return_value=[
                {"provider": provider},
                {"error": "provider timeout"},
            ],
        ),
        pytest.raises(RuntimeError, match="provider timeout"),
    ):
        fetch_organization_history("917432254", "insee")


def test_untyped_open_relation_constraints_are_declared():
    relation_constraints = {
        constraint.name
        for constraint in OrganizationAtlasOrganizationRelation._meta.constraints
    }
    stakeholder_constraints = {
        constraint.name
        for constraint in OrganizationAtlasStakeholderRelation._meta.constraints
    }

    assert "unique_open_untyped_organization_relation" in relation_constraints
    assert "unique_open_untyped_stakeholder_relation" in stakeholder_constraints


@pytest.mark.django_db
def test_untyped_open_relation_constraints_are_enforced():
    holder = _organization()
    target = OrganizationAtlasOrganization.objects.create(
        denomination="Target",
        code="123456789",
        source="insee",
        country_code="FR",
    )
    OrganizationAtlasOrganizationRelation.objects.create(
        from_organization=holder,
        to_organization=target,
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        OrganizationAtlasOrganizationRelation.objects.create(
            from_organization=holder,
            to_organization=target,
        )

    content_type = ContentType.objects.get_for_model(holder)
    OrganizationAtlasStakeholderRelation.objects.create(
        content_type=content_type,
        object_id=holder.pk,
        to_organization=target,
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        OrganizationAtlasStakeholderRelation.objects.create(
            content_type=content_type,
            object_id=holder.pk,
            to_organization=target,
        )


@pytest.mark.django_db
def test_load_history_form_saves_provider_rows():
    organization = _organization()
    client = _client()

    with patch(
        "django_organizationatlas.admin.organization.load_organization_history",
        return_value=3,
    ) as load:
        response = client.post(_url("load_history", organization), {"provider": "insee"})

    assert response.status_code == 302
    assert response.url == _url("change", organization)
    load.assert_called_once()
    assert load.call_args.args[1] == "insee"


@pytest.mark.django_db
def test_load_history_form_hides_provider_error_details():
    organization = _organization()
    client = _client()

    with patch(
        "django_organizationatlas.admin.organization.load_organization_history",
        side_effect=RuntimeError("secret provider URL"),
    ):
        response = client.post(_url("load_history", organization), {"provider": "insee"})

    html = response.content.decode()
    assert response.status_code == 200
    assert "Organization history load failed." in html
    assert "secret provider URL" not in html
