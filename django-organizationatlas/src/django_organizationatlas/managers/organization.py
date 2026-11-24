from django.db import models
from django.db.models import Count, IntegerField, OuterRef, Prefetch, Subquery


class OrganizationAtlasOrganizationQuerySet(models.QuerySet):
    def with_same_code_count(self):
        """Count all organizations with the same code, including this one."""
        counts = (
            self.model._base_manager.using(self.db)
            .filter(code=OuterRef('code'))
            .order_by()
            .values('code')
            .annotate(total=Count('pk'))
            .values('total')
        )
        return self.annotate(
            sql_same_code_count=Subquery(counts, output_field=IntegerField()),
        )

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
