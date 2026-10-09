"""URL configuration for tests."""

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

try:
    import djrichtextfield
    urlpatterns += [
        path("djrichtextfield/", include("djrichtextfield.urls")),
    ]
except ImportError:
    pass

_version = f"(Django {django.get_version()}, organizationatlas {organizationatlas.__version__}/{django_organizationatlas.__version__})"
admin.site.site_header = f"Django OrganizationAtlas - Administration {_version}"
admin.site.site_title = f"Django OrganizationAtlas Admin {_version}"
admin.site.index_title = f"Welcome to Django OrganizationAtlas {_version}"
