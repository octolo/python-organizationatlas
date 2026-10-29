from django.db import models
from django.db.models import Prefetch


class OrganizationAtlasOrganizationQuerySet(models.QuerySet):
    def with_related(self):
        return self.prefetch_related("to_organizationatlasdata", "to_organizationatlasaddress")

    def with_headquarters(self):
        from ..models.address import OrganizationAtlasAddress
        return self.prefetch_related(
            Prefetch(
                "to_organizationatlasaddress",
                queryset=OrganizationAtlasAddress.objects.filter(
                    is_headquarters=True,
                    valid_to__isnull=True,
                ),
                to_attr="prefetched_headquarters",
            )
        )


class OrganizationAtlasOrganizationManager(models.Manager):
    def get_queryset(self):
        return OrganizationAtlasOrganizationQuerySet(self.model, using=self._db)
