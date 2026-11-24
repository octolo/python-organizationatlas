from django.core.exceptions import ValidationError
from django.db import NotSupportedError, models, transaction
from django.db.models import Case, Count, F, IntegerField, OuterRef, Q, Subquery, Value, When
from django.db.models.functions import Coalesce, TruncDate
from django.db.models.lookups import IsNull
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from ..category_names import category_name, category_name_expression, data_type_name
from ..country_codes import GLOBAL_COUNTRY_CODE
from ..models.reference import (
    OrganizationAtlasReference,
    OrganizationAtlasReferenceCategory,
)
from ..visual_identity import visual_identity_data_type


class OrganizationAtlasDataTypeQuerySet(models.QuerySet):
    def update(self, **kwargs):
        if {'category', 'category_id'}.intersection(kwargs):
            raise NotSupportedError(
                'Update data type categories with model save().',
            )
        return super().update(**kwargs)


class OrganizationAtlasDataTypeManager(
    models.Manager.from_queryset(OrganizationAtlasDataTypeQuerySet),
):
    def for_key(self, data_type, value_type='str', *, category=None):
        obj, created = self.get_or_create(
            data_type=data_type,
            category=category,
            defaults={'value_type': value_type},
        )
        if not created and obj.value_type != value_type:
            raise ValueError(
                f'data type {data_type!r} already uses value type '
                f'{obj.value_type!r}, not {value_type!r}'
            )
        return obj

    def reference_data_type(self, reference):
        identity = visual_identity_data_type(reference)
        if identity:
            return identity
        if (reference.default_value or '').strip():
            name = reference.code
        else:
            name = data_type_name(reference.category.name)
        value_type = (
            self.filter(data_type=name, category=reference.category)
            .values_list('value_type', flat=True)
            .first()
        )
        if value_type is None:
            value_type = (
                self.filter(
                    data_type=name, category__isnull=True,
                    records__isnull=True,
                )
                .values_list('value_type', flat=True)
                .first()
            )
        return name, value_type or 'str'

    def for_reference(self, reference):
        with transaction.atomic(using=self.db):
            name, value_type = self.reference_data_type(reference)
            existing = self.filter(
                data_type=name, category=reference.category,
            ).first()
            if existing is not None:
                return self.for_key(
                    name, value_type, category=reference.category,
                )
            unassigned = self.select_for_update().filter(
                data_type=name, category__isnull=True,
            ).first()
            if unassigned is not None:
                if unassigned.records.exists():
                    raise ValidationError(
                        _(
                            'Associate the existing data type with a category '
                            'or create the category-specific type first.'
                        ),
                    )
                if unassigned.value_type != value_type:
                    raise ValueError(
                        f'data type {name!r} already uses value type '
                        f'{unassigned.value_type!r}, not {value_type!r}'
                    )
                unassigned.category = reference.category
                unassigned.save(update_fields=['category'])
                return unassigned
            return self.for_key(
                name, value_type, category=reference.category,
            )

    def for_provider(self, data_type, value_type, country):
        categories = OrganizationAtlasReferenceCategory.objects.filter(
            name=category_name(data_type),
            country_code__in=[country, GLOBAL_COUNTRY_CODE],
        ).order_by(
            Case(
                When(country_code=country, then=Value(0)),
                default=Value(1),
            ),
        )
        category = categories.first()
        if category and not self.filter(
            data_type=data_type, category=category,
        ).exists() and self.filter(
            data_type=data_type, category__isnull=True,
        ).filter(
            Q(records__country_code=country)
            | Q(
                records__country_code__in=['', 'XX'],
                records__organization__country_code=country,
            ),
        ).exists():
            category = None
        return self.for_key(data_type, value_type, category=category)


def start_at_expression():
    """Return the validity date, falling back to the recorded date."""
    return Coalesce('valid_from', TruncDate('created_at'))


class OrganizationAtlasDataQuerySet(models.QuerySet):
    def active(self):
        return self.filter(
            Q(valid_to__isnull=True) | Q(valid_to__gt=timezone.localdate()),
        )

    def update(self, **kwargs):
        guarded = {
            'organization', 'organization_id', 'data_type', 'data_type_id',
            'valid_to', 'main', 'source', 'country_code', 'metadata',
        }
        if guarded.intersection(kwargs):
            raise NotSupportedError(
                'Update data validity and identity with model save().',
            )
        return super().update(**kwargs)

    def bulk_create(self, *args, **kwargs):
        raise NotSupportedError('Create data records with model save().')

    def with_start_at(self):
        """Annotate the date used for display and ordering."""
        return self.annotate(start_at=start_at_expression())

    def with_data_reference(self):
        """Description of the reference whose category matches the data type and whose code is the value."""
        reference = OrganizationAtlasReference.objects.filter(
            Q(category_id=OuterRef('data_type__category_id'))
            | (
                Q(IsNull(OuterRef('data_type__category_id'), True))
                & Q(category__name=OuterRef("reference_category_name"))
                & (
                    Q(category__country_code=OuterRef("reference_country"))
                    | Q(category__country_code=GLOBAL_COUNTRY_CODE)
                )
            ),
            display_code=OuterRef("value"),
        ).annotate(
            country_priority=Case(
                When(
                    category__country_code=GLOBAL_COUNTRY_CODE,
                    then=Value(1),
                ),
                default=Value(0),
            ),
        ).order_by('country_priority', '-priority')
        return self.annotate(
            reference_category_name=category_name_expression(
                'data_type__data_type',
            ),
            reference_country=Case(
                When(country_code__in=["", "XX"], then=F("organization__country_code")),
                default=F("country_code"),
            ),
        ).annotate(
            sql_data_reference=Subquery(reference.values("description")[:1]),
        )

    def with_older_count(self):
        """Number of closed records of the same data type on the same organization."""
        older = (
            self.model.objects.filter(
                organization_id=OuterRef("organization_id"),
                data_type_id=OuterRef("data_type_id"),
                valid_to__lte=timezone.localdate(),
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
