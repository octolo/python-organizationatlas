"""Views for organizationatlas app."""

import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render

from .models import OrganizationAtlasOrganization

logger = logging.getLogger(__name__)


@login_required
@permission_required(
    "django_organizationatlas.view_organizationatlasorganization",
    raise_exception=True,
)
def organization_list(request):
    """List all organizations."""
    organizations = Paginator(
        OrganizationAtlasOrganization.objects.all(),
        25,
    ).get_page(request.GET.get("page"))
    context = {
        "organizations": organizations,
    }
    return render(request, "django_organizationatlas/organization_list.html", context)


@login_required
@permission_required(
    "django_organizationatlas.view_organizationatlasorganization",
    raise_exception=True,
)
def organization_detail(request, pk):
    """Show organization details."""
    organization = get_object_or_404(OrganizationAtlasOrganization, pk=pk)
    context = {
        "organization": organization,
    }
    return render(request, "django_organizationatlas/organization_detail.html", context)


@permission_required(
    "django_organizationatlas.change_organizationatlasorganization",
    raise_exception=True,
)
def organization_enrich(request, pk):
    """Trigger organization enrichment."""
    organization = get_object_or_404(OrganizationAtlasOrganization, pk=pk)

    if request.method == "POST":
        try:
            enriched = organization.enrich()
        except Exception:
            logger.exception(
                "Organization enrichment failed",
                extra={"organization_id": organization.pk},
            )
            enriched = False
        if enriched:
            messages.success(request, f"Successfully enriched {organization.denomination}")
        else:
            messages.error(request, f"Failed to enrich {organization.denomination}")
        return redirect("django_organizationatlas:organization-detail", pk=pk)

    return render(request, "django_organizationatlas/organization_enrich.html", {"organization": organization})
