from django.db import models
from django.db.models import Count, IntegerField, OuterRef, Subquery, Value
from django.db.models.functions import Coalesce

from ..models.reference import OrganizationAtlasReference


class OrganizationAtlasDataQuerySet(models.QuerySet):
    def with_data_reference(self):
        """Description of the reference whose category matches the data type and whose code is the value."""
        reference = OrganizationAtlasReference.objects.filter(
            category__name=OuterRef("data_type__data_type"),
            code=OuterRef("value"),
        ).order_by("-priority")
        return self.annotate(
            sql_data_reference=Subquery(reference.values("description")[:1]),
        )

    def with_older_count(self):
        """Number of closed records of the same data type on the same organization."""
        older = (
            self.model.objects.filter(
                organization_id=OuterRef("organization_id"),
                data_type_id=OuterRef("data_type_id"),
                valid_to__isnull=False,
            )
            .order_by()
            .values("data_type_id")
            .annotate(total=Count("pk"))
            .values("total")
        )
        return self.annotate(
            sql_older_count=Coalesce(
                Subquery(older, output_field=IntegerField()),
                Value(0),
            ),
        )


OrganizationAtlasDataManager = models.Manager.from_queryset(OrganizationAtlasDataQuerySet)
