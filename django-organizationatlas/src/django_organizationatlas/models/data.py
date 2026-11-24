"""Organization data models."""

import json
from datetime import date
from typing import Any

from django import forms
from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction
from django.db.models import Count, Q, Value
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Coalesce
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django_boosted import get_current_user

from ..category_names import category_name
from ..country_codes import GLOBAL_COUNTRY_CODE
from ..managers.data import (
    OrganizationAtlasDataManager,
    OrganizationAtlasDataTypeManager,
)
from ..reference_codes import normalize_reference_code
from ..storage import data_file_storage, data_file_upload_to
from .organization import OrganizationAtlasOrganization
from .reference import OrganizationAtlasReference, OrganizationAtlasReferenceCategory
from .source import OrganizationAtlasSourceBase, USER_COUNTRY_CODE
from .temporal import TemporalValidityMixin

VALUE_TYPE_CHOICES = [
    ("str", _("String")),
    ("int", _("Integer")),
    ("float", _("Float")),
    ("bool", _("Boolean")),
    ("date", _("Date")),
    ("json", _("JSON")),
    ('image', _('Image')),
    ('file', _('File')),
]


def reference_for_value(
    data_type: str, country: str, value: str, *, category_id=None,
):
    """Find a value reference, preferring the specified country."""
    categories = (
        Q(category_id=category_id)
        if category_id
        else Q(
            category__name=category_name(data_type),
            category__country_code__in=[country, GLOBAL_COUNTRY_CODE],
        )
    )
    return (
        OrganizationAtlasReference.objects.filter(
            categories,
            code=normalize_reference_code(value),
            default_value='',
        )
        .order_by(
            models.Case(
                models.When(category__country_code=country, then=0),
                default=1,
            ),
            '-priority',
        )
        .first()
    )


def reference_value(
    data_type: str, country: str, value: str, *, category_id=None,
) -> str:
    """Return a known reference's display code, or the unchanged value."""
    reference = reference_for_value(
        data_type, country, value, category_id=category_id,
    )
    return reference.display_code if reference is not None else value


class OrganizationAtlasDataType(models.Model):
    """Shared definition of a data key and the type of its value."""

    data_type = models.CharField(
        max_length=100,
        verbose_name=_("Data Type"),
        help_text=_("Type of data (e.g., denomination, siren, capital, employees)"),
    )
    value_type = models.CharField(
        max_length=10,
        verbose_name=_("Value Type"),
        choices=VALUE_TYPE_CHOICES,
        default="str",
        help_text=_('Type of the value (str, int, float, bool, date, json, image, file)'),
    )
    category = models.ForeignKey(
        'django_organizationatlas.OrganizationAtlasReferenceCategory',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='data_types',
        verbose_name=_('Reference category'),
    )

    objects = OrganizationAtlasDataTypeManager()

    class Meta:
        verbose_name = _("Data Type")
        verbose_name_plural = _("Data Types")
        ordering = ["data_type"]
        constraints = [
            models.UniqueConstraint(
                fields=['data_type', 'category'],
                condition=Q(category__isnull=False),
                name='unique_datatype_category',
            ),
            models.UniqueConstraint(
                fields=['data_type'],
                condition=Q(category__isnull=True),
                name='unique_datatype_without_category',
            ),
        ]

    def __str__(self):
        return self.data_type

    def clean(self):
        super().clean()
        self._validate_category()

    def _validate_category(self):
        if not self.pk or not self.category_id:
            return
        active = OrganizationAtlasData.objects.filter(
            Q(valid_to__isnull=True) | Q(valid_to__gt=timezone.localdate()),
            data_type_id=self.pk,
        )
        if not self.category.unique:
            active = active.filter(main=True)
        if (
            active.values('organization_id')
            .annotate(total=Count('pk'))
            .filter(total__gt=1)
            .exists()
        ):
            raise ValidationError({
                'category': _(
                    'Resolve conflicting active data before assigning '
                    'this category.'
                ),
            })

    def save(self, *args, **kwargs):
        update_fields = kwargs.get('update_fields')
        if not self.pk or (
            update_fields is not None
            and not {'category', 'category_id'}.intersection(update_fields)
        ):
            return super().save(*args, **kwargs)
        with transaction.atomic(using=kwargs.get('using')):
            type(self).objects.select_for_update().get(pk=self.pk)
            if self.category_id:
                self.category = OrganizationAtlasReferenceCategory.objects.select_for_update().get(
                    pk=self.category_id,
                )
            self._validate_category()
            return super().save(*args, **kwargs)

    @classmethod
    def for_key(
        cls, data_type: str, value_type: str = "str", *, category=None,
    ):
        """Return the shared type, creating it with value_type only the first time."""
        return cls.objects.for_key(data_type, value_type, category=category)


class OrganizationAtlasData(TemporalValidityMixin, OrganizationAtlasSourceBase):
    """Organization data from various backends."""

    temporal_key_fields = ("organization", "source", "country_code", "data_type")

    organization = models.ForeignKey(
        OrganizationAtlasOrganization,
        on_delete=models.CASCADE,
        related_name="to_organizationatlasdata",
        verbose_name=_("Organization"),
        help_text=_("Organization this data belongs to"),
    )
    data_type = models.ForeignKey(
        OrganizationAtlasDataType,
        on_delete=models.PROTECT,
        related_name="records",
        verbose_name=_("Data Type"),
        help_text=_("Shared data type. Its value type applies to every record."),
    )
    value = models.TextField(
        blank=True,
        verbose_name=_("Value"),
        help_text=_("Data value"),
    )
    file = models.FileField(
        upload_to=data_file_upload_to,
        storage=data_file_storage,
        blank=True,
        verbose_name=_('File'),
        help_text=_('File or image associated with this data.'),
    )
    main = models.BooleanField(
        default=False,
        verbose_name=_('Main'),
        help_text=_('Whether this data is marked as main.'),
    )
    reference = models.ManyToManyField(
        OrganizationAtlasReference,
        verbose_name=_("Reference"),
        help_text=_("Reference this data belongs to"),
        related_name="to_organizationatlasdata",
        blank=True,
    )

    class Meta:
        verbose_name = _("Data")
        verbose_name_plural = _("Data")
        indexes = [
            models.Index(fields=["organization", "country_code"]),
        ]
        ordering = ["data_type__data_type", "-created_at"]

    objects = OrganizationAtlasDataManager()

    @property
    def is_current(self):
        return self.valid_to is None or self.valid_to > timezone.localdate()

    def _validate_single_open_record(self):
        if self.data_type_id and self.data_type.category_id:
            return
        super()._validate_single_open_record()

    @property
    def typed_value(self) -> Any:
        value_type = self.data_type.value_type
        if value_type in {'image', 'file'}:
            return self.file
        if value_type == "str":
            return self.value
        if value_type == "int":
            return int(self.value)
        if value_type == "float":
            return float(self.value)
        if value_type == "bool":
            normalized = self.value.strip().lower()
            if normalized in {"true", "1", "yes", "on"}:
                return True
            if normalized in {"false", "0", "no", "off"}:
                return False
            raise ValueError("expected a boolean value")
        if value_type == "date":
            return date.fromisoformat(self.value)
        if value_type == "json":
            return json.loads(self.value)
        raise ValueError(f"unsupported value type: {value_type}")

    def clean(self):
        super().clean()
        if not self.data_type_id:
            return
        if self.data_type.value_type in {'image', 'file'}:
            if not self.file:
                raise ValidationError({'file': _('A file is required.')})
            if self.value:
                raise ValidationError({'value': _('Leave value empty for files.')})
            if self.data_type.value_type == 'image':
                try:
                    forms.ImageField().clean(self.file)
                except ValidationError as exc:
                    raise ValidationError({'file': exc.messages}) from exc
            return
        if self.file:
            raise ValidationError({'file': _('Files require a file or image type.')})
        if not self.value:
            raise ValidationError({'value': _('A value is required.')})
        try:
            self.typed_value
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValidationError(
                {"value": _("Value does not match the declared data type.")}
            ) from exc

    def save(self, *args, normalize_reference=True, **kwargs):
        update_fields = kwargs.get("update_fields")
        if (
            normalize_reference
            and self.data_type_id
            and self.organization_id
            and isinstance(self.value, str)
            and self.data_type.value_type == "str"
            and (update_fields is None or "value" in update_fields)
        ):
            country = self.country_code
            if not country or country == USER_COUNTRY_CODE:
                country = self.organization.country_code or ""
            display = reference_value(
                self.data_type.data_type, country, self.value,
                category_id=self.data_type.category_id,
            )
            if display != self.value:
                category_filter = (
                    Q(category_id=self.data_type.category_id)
                    if self.data_type.category_id
                    else Q(category__name=category_name(self.data_type.data_type))
                )
                dynamic_reference = self.pk and self.reference.filter(
                    ~category_filter
                    | Q(default_value__gt=""),
                ).exists()
                if not dynamic_reference:
                    self.value = display
        guarded_fields = {
            'organization', 'data_type', 'valid_to', 'main',
            'source', 'country_code', 'metadata',
        }
        guarded_fields.update({'organization_id', 'data_type_id'})
        if (
            update_fields is not None
            and not guarded_fields.intersection(update_fields)
        ):
            return super().save(*args, **kwargs)
        with transaction.atomic(using=kwargs.get('using')):
            candidate = self
            if update_fields is not None and self.pk:
                candidate = type(self).objects.get(pk=self.pk)
                for field in guarded_fields.intersection(update_fields):
                    setattr(candidate, field, getattr(self, field))
            candidate._apply_data_rules()
            return super().save(*args, **kwargs)

    def _apply_data_rules(self):
        if not self.organization_id or not self.data_type_id:
            return
        OrganizationAtlasOrganization.objects.select_for_update().get(
            pk=self.organization_id,
        )
        datatype = OrganizationAtlasDataType.objects.select_for_update().get(
            pk=self.data_type_id,
        )
        category = None
        if datatype.category_id:
            category = OrganizationAtlasReferenceCategory.objects.select_for_update().get(
                pk=datatype.category_id,
            )
        if category is None:
            self._check_uncategorized_open_record()
        elif self.is_current and category.unique:
            self._close_other_active_data()
        elif self.is_current and self.main:
            self._clear_other_main_data()

    def _active_data(self):
        today = timezone.localdate()
        return type(self).objects.filter(
            Q(valid_to__isnull=True) | Q(valid_to__gt=today),
            organization_id=self.organization_id,
            data_type_id=self.data_type_id,
        ).exclude(pk=self.pk)

    def _close_other_active_data(self):
        today = timezone.localdate()
        for row in self._active_data().select_for_update():
            if row.valid_from and row.valid_from > today:
                raise ValidationError(
                    _('Cannot close a data period before its start date.'),
                )
            row.valid_to = today
            row.save(update_fields=['valid_to', 'updated_at'])

    def _clear_other_main_data(self):
        for row in self._active_data().filter(main=True).select_for_update():
            row.main = False
            row.save(update_fields=['main', 'updated_at'])

    def _check_uncategorized_open_record(self):
        if self.valid_to is not None:
            return
        source = self.source
        country = self.country_code
        user = get_current_user()
        if not source and user is not None and user.is_authenticated and user.pk:
            source = self._manual_source(user)
            country = country or USER_COUNTRY_CODE
        trace = (self.metadata or {}).get('trace') or ''
        duplicates = (
            type(self).objects.filter(
                organization_id=self.organization_id,
                data_type_id=self.data_type_id,
                source=source,
                country_code=country,
                valid_to__isnull=True,
            )
            .exclude(pk=self.pk)
            .annotate(
                trace_key=Coalesce(
                    KeyTextTransform('trace', 'metadata'), Value(''),
                    output_field=models.TextField(),
                ),
            )
            .filter(trace_key=trace)
        )
        if duplicates.exists():
            raise IntegrityError(
                'An open data record already exists for this key.',
            )

    def __str__(self):
        return (
            f"{self.organization.denomination} - {self.source} - "
            f"{self.country_code} - {self.data_type}"
        )

    def data_reference(self):
        if hasattr(self, "sql_data_reference"):
            return self.sql_data_reference or ""
        if not self.data_type_id:
            return ""
        categories = (
            Q(category_id=self.data_type.category_id)
            if self.data_type.category_id
            else Q(
                category__name=category_name(self.data_type.data_type),
                category__country_code__in=[
                    self.organization.country_code
                    if self.country_code in ("", USER_COUNTRY_CODE)
                    else self.country_code,
                    GLOBAL_COUNTRY_CODE,
                ],
            )
        )
        description = (
            OrganizationAtlasReference.objects.filter(
                categories,
                display_code=self.value,
            )
            .order_by(
                models.Case(
                    models.When(
                        category__country_code=(
                            self.organization.country_code
                            if self.country_code in ("", USER_COUNTRY_CODE)
                            else self.country_code
                        ),
                        then=0,
                    ),
                    default=1,
                ),
                "-priority",
            )
            .values_list("description", flat=True)
            .first()
        )
        return description or ""
    data_reference.short_description = _("Reference")
    data_reference = property(data_reference)

    @property
    def reference_description(self):
        if hasattr(self, "sql_reference_description"):
            return self.sql_reference_description
        first = self.reference.values_list("description", flat=True).first()
        return first or ""
