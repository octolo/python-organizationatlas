"""Smoke test so the Django package has something for CI to collect."""


def test_app_is_installed():
    from django.apps import apps

    assert apps.is_installed("django_organizationatlas")
