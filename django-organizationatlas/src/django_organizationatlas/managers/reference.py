from django.db import NotSupportedError, models
from django.db.models import (
    Case, Count, Exists, F, IntegerField, OuterRef, Q, Subquery, Value, When,
)
from django.db.models.lookups import Exact

from ..category_names import category_name_expression
from ..country_codes import GLOBAL_COUNTRY_CODE

FEATURE_CATEGORY = "feature"


class OrganizationAtlasReferenceCategoryQuerySet(models.QuerySet):
    def update(self, **kwargs):
        if 'unique' in kwargs:
            raise NotSupportedError('Update category uniqueness with model save().')
        return super().update(**kwargs)

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

        specific = self.model.objects.filter(
            category__name=OuterRef("reference_category_name"),
            category__country_code=OuterRef("lookup_country"),
            display_code=OuterRef("value"),
        ).exclude(category__country_code=GLOBAL_COUNTRY_CODE)
        usage = (
            OrganizationAtlasData.objects.annotate(
                reference_category_name=category_name_expression(
                    'data_type__data_type',
                ),
                lookup_country=Case(
                    When(
                        country_code__in=["", "XX"],
                        then=F("organization__country_code"),
                    ),
                    default=F("country_code"),
                ),
                has_specific_reference=Exists(specific),
            ).filter(
                Q(data_type__category_id=OuterRef('category_id'))
                | (
                    Q(data_type__category__isnull=True)
                    & Q(reference_category_name=OuterRef("category__name"))
                    & (
                        Q(lookup_country=OuterRef("category__country_code"))
                        | Q(
                            Exact(
                                OuterRef("category__country_code"),
                                Value(GLOBAL_COUNTRY_CODE),
                            ),
                            has_specific_reference=False,
                        )
                    )
                ),
                value=OuterRef("display_code"),
            )
            .active()
            .order_by()
            .values("pk")
        )
        return self.annotate(sql_used_count=_CountSubquery(usage))

    def with_has_data_type(self):
        """Annotate has_data_type when the category name matches a data type."""
        from ..models.data import OrganizationAtlasDataType

        match = OrganizationAtlasDataType.objects.annotate(
            reference_category_name=category_name_expression('data_type'),
        ).filter(
            Q(category_id=OuterRef('category_id'))
            | Q(
                category__isnull=True,
                reference_category_name=OuterRef("category__name"),
            ),
        )
        return self.annotate(has_data_type=Exists(match))

    def features(self):
        """References tagged as features."""
        return self.filter(category__name=FEATURE_CATEGORY)


OrganizationAtlasReferenceManager = models.Manager.from_queryset(OrganizationAtlasReferenceQuerySet)
