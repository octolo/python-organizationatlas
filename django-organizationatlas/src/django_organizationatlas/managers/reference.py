from django.db import models
from django.db.models import Count, Exists, IntegerField, OuterRef, Subquery


class OrganizationAtlasReferenceCategoryQuerySet(models.QuerySet):
    def with_reference_count(self):
        return self.annotate(sql_reference_count=Count("references"))


OrganizationAtlasReferenceCategoryManager = models.Manager.from_queryset(
    OrganizationAtlasReferenceCategoryQuerySet,
)


class _CountSubquery(Subquery):
    template = "(SELECT COUNT(*) FROM (%(subquery)s) _count)"
    output_field = IntegerField()


class OrganizationAtlasReferenceQuerySet(models.QuerySet):
    def with_usage_count(self):
        """Count current data rows whose type is the category and whose value is the code."""
        from ..models.data import OrganizationAtlasData

        usage = (
            OrganizationAtlasData.objects.filter(
                data_type__data_type=OuterRef("category__name"),
                value=OuterRef("code"),
                valid_to__isnull=True,
            )
            .order_by()
            .values("pk")
        )
        return self.annotate(sql_used_count=_CountSubquery(usage))

    def with_has_data_type(self):
        """Annotate has_data_type when the category name matches a data type."""
        from ..models.data import OrganizationAtlasDataType

        match = OrganizationAtlasDataType.objects.filter(
            data_type=OuterRef("category__name"),
        )
        return self.annotate(has_data_type=Exists(match))


OrganizationAtlasReferenceManager = models.Manager.from_queryset(OrganizationAtlasReferenceQuerySet)
