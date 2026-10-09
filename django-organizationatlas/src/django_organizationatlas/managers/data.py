from django.db import models
from django.db.models import OuterRef, Subquery

from ..models.reference import OrganizationAtlasReference


class OrganizationAtlasDataQuerySet(models.QuerySet):
    def with_reference_description(self):
        return self.annotate(
            sql_reference_description=Subquery(
                OrganizationAtlasReference.objects.filter(
                    pk=OuterRef("reference"),
                ).values("description")[:1],
            ),
        )

    def with_data_reference(self):
        """Description of the reference whose category matches the data type and whose code is the value."""
        reference = OrganizationAtlasReference.objects.filter(
            category__name=OuterRef("data_type__data_type"),
            code=OuterRef("value"),
        ).order_by("-priority")
        return self.annotate(
            sql_data_reference=Subquery(reference.values("description")[:1]),
        )


OrganizationAtlasDataManager = models.Manager.from_queryset(OrganizationAtlasDataQuerySet)
