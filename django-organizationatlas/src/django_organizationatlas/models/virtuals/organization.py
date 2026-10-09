"""Organization suggestion model for organizationatlas."""

from typing import Any

from organizationatlas.providers import get_search_organization_fields
from django.db import models
from django.utils.translation import gettext_lazy as _
from django_providerkit.models.define import define_fields_from_config
from virtualqueryset.models import VirtualModel

from django_organizationatlas.helpers import create_organization
from django_organizationatlas.managers.virtuals.organization import OrganizationAtlasVirtualOrganizationManager

FIELDS_ORGANIZATIONATLAS = get_search_organization_fields()

organizationatlas_id_config: dict[str, Any] = FIELDS_ORGANIZATIONATLAS['organizationatlas_id']


@define_fields_from_config(FIELDS_ORGANIZATIONATLAS, primary_key='organizationatlas_id')
class OrganizationAtlasVirtualOrganization(VirtualModel):
    """Virtual model for organization suggestions from organizationatlas."""

    organizationatlas_id: models.CharField = models.CharField(
        max_length=500,
        verbose_name=organizationatlas_id_config['label'],
        help_text=organizationatlas_id_config['description'],
        primary_key=True,
    )

    objects = OrganizationAtlasVirtualOrganizationManager()

    class Meta:
        managed = False
        verbose_name = _('Virtual Organization')
        verbose_name_plural = _('Virtual Organizations')

    def __str__(self) -> str:
        denomination = getattr(self, 'denomination', None)
        organizationatlas_id = getattr(self, 'organizationatlas_id', None)
        if denomination:
            return str(denomination)
        return f"Organization {organizationatlas_id or 'unknown'}"

    def create_organization(self):
        return create_organization(self)
