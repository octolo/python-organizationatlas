"""URL configuration for tests."""

from importlib.util import find_spec

import django
import organizationatlas
import django_organizationatlas
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    path("", RedirectView.as_view(url="/admin/", permanent=False)),
    path("admin/", admin.site.urls),
    path("organizations/", include("django_organizationatlas.urls")),
    path("geoaddress/", include("django_geoaddress.urls")),
]

if find_spec("djrichtextfield") is not None:
    urlpatterns += [
        path("djrichtextfield/", include("djrichtextfield.urls")),
    ]

_version = f"(Django {django.get_version()}, organizationatlas {organizationatlas.__version__}/{django_organizationatlas.__version__})"
admin.site.site_header = f"Django OrganizationAtlas - Administration {_version}"
admin.site.site_title = f"Django OrganizationAtlas Admin {_version}"
admin.site.index_title = f"Welcome to Django OrganizationAtlas {_version}"
