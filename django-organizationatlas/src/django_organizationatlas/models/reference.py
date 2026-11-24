from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Count, Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django_boosted import get_current_user

from ..category_names import category_name, data_type_name
from ..country_codes import GLOBAL_COUNTRY_CODE
from ..reference_codes import normalize_reference_code
from ..managers.reference import (
    OrganizationAtlasReferenceCategoryManager,
    OrganizationAtlasReferenceManager,
)
from ..visual_identity import VISUAL_IDENTITY_CATEGORY
from .source import OrganizationAtlasSourceBase


def category_default_unique(name):
    """Return the default uniqueness for an automatically created category."""
    return name not in {VISUAL_IDENTITY_CATEGORY, 'API trace'}


class OrganizationAtlasReferenceCategory(models.Model):
    """Named group of reference codes for one country, such as ape or legalform."""

    name = models.CharField(
        max_length=255,
        verbose_name=_("Name"),
        help_text=_("Category name, for example ape or legalform"),
    )
    country_code = models.CharField(
        max_length=2,
        verbose_name=_("Country code"),
        help_text=_("ISO country code this category belongs to"),
    )
    description = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Description"),
        help_text=_("Category label"),
    )
    unique = models.BooleanField(
        default=True,
        verbose_name=_('Unique'),
        help_text=_('Whether this category allows only one value.'),
    )

    objects = OrganizationAtlasReferenceCategoryManager()

    class Meta:
        verbose_name = _("Reference category")
        verbose_name_plural = _("Reference categories")
        ordering = ["country_code", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["name", "country_code"],
                name="unique_reference_category_country",
            ),
        ]

    def __str__(self):
        if not self.country_code:
            return self.name
        return f"{self.country_code}/{self.name}"

    def clean(self):
        super().clean()
        self._validate_unique_data()

    def _validate_unique_data(self):
        if not self.pk or not self.unique:
            return
        from .data import OrganizationAtlasData

        duplicates = (
            OrganizationAtlasData.objects.filter(
                Q(valid_to__isnull=True)
                | Q(valid_to__gt=timezone.localdate()),
                data_type__category_id=self.pk,
            )
            .values('organization_id', 'data_type_id')
            .annotate(total=Count('pk'))
            .filter(total__gt=1)
        )
        if duplicates.exists():
            raise ValidationError({
                'unique': _(
                    'Resolve active data duplicates before enabling uniqueness.'
                ),
            })

    def save(self, *args, **kwargs):
        if not self.country_code:
            self.country_code = GLOBAL_COUNTRY_CODE
        update_fields = kwargs.get('update_fields')
        if not self.pk or (
            update_fields is not None and 'unique' not in update_fields
        ):
            return super().save(*args, **kwargs)
        with transaction.atomic(using=kwargs.get('using')):
            type(self).objects.select_for_update().get(pk=self.pk)
            self._validate_unique_data()
            return super().save(*args, **kwargs)

    @classmethod
    def for_name(cls, name: str, country_code: str):
        name = category_name(name)
        country_code = country_code or GLOBAL_COUNTRY_CODE
        category, _created = cls.objects.get_or_create(
            name=name,
            country_code=country_code,
            defaults={'unique': category_default_unique(name)},
        )
        return category


class OrganizationAtlasReference(OrganizationAtlasSourceBase):
    """One code inside a reference category."""

    category = models.ForeignKey(
        OrganizationAtlasReferenceCategory,
        on_delete=models.PROTECT,
        related_name="references",
        verbose_name=_("Category"),
        help_text=_("Category this code belongs to"),
    )
    source_category = models.ForeignKey(
        OrganizationAtlasReferenceCategory,
        on_delete=models.SET_NULL,
        related_name="source_references",
        null=True,
        blank=True,
        verbose_name=_("Source category"),
        help_text=_("Optional source category, for example law, articles or a shareholders' agreement"),
    )
    code = models.CharField(
        max_length=255,
        verbose_name=_("Code"),
        help_text=_("Reference code"),
    )
    display_code = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name=_("Display code"),
        help_text=_("Display form of the reference code."),
    )
    description = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Description"),
        help_text=_("Reference description"),
    )
    characteristics = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Characteristics"),
        help_text=_("Reference characteristics"),
    )
    priority = models.IntegerField(
        verbose_name=_("Priority"),
        help_text=_("Reference priority"),
        default=0,
    )
    default_value = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name=_("Default value"),
        help_text=_("Optional default value. Empty when the reference has none, for example 50% for a majority."),
    )

    objects: OrganizationAtlasReferenceManager = OrganizationAtlasReferenceManager()

    class Meta:
        verbose_name = _("Reference")
        verbose_name_plural = _("References")
        ordering = ["-priority", "category__name", "code"]
        constraints = [
            models.UniqueConstraint(
                fields=["category", "code"],
                name="unique_reference_category_code",
            ),
        ]
        indexes = [
            models.Index(
                fields=["category", "display_code"],
                name="oa_ref_category_display_idx",
            ),
        ]

    def __str__(self):
        return f"{self.display_code} - {self.description}"

    def _normalize_code(self):
        if not self.display_code:
            self.display_code = self.code.strip()
        self.code = normalize_reference_code(self.code)
        if not self.code or len(self.code) > 255:
            raise ValidationError({"code": _("Invalid reference code.")})
        if normalize_reference_code(self.display_code) != self.code:
            raise ValidationError(
                {"display_code": _("Display code must match the reference code.")}
            )

    def clean(self):
        super().clean()
        self._normalize_code()
        self._validate_code_change()

    def _validate_code_change(self):
        if not self.pk:
            return
        previous = type(self).objects.filter(pk=self.pk).first()
        if not previous or (
            previous.category_id == self.category_id
            and previous.code == self.code
            and previous.display_code == self.display_code
        ):
            return
        from .data import OrganizationAtlasData

        used_as_value = OrganizationAtlasData.objects.filter(
            Q(data_type__category_id=previous.category_id)
            | Q(
                data_type__category__isnull=True,
                data_type__data_type=data_type_name(previous.category.name),
            ),
            value=previous.display_code,
        ).exists()
        if used_as_value or previous.to_organizationatlasdata.exists():
            raise ValidationError(
                _("A reference used by data cannot change its category or code.")
            )

    def save(self, *args, **kwargs):
        user = get_current_user()
        manual_source = (
            not self.source
            and user is not None
            and user.is_authenticated
            and user.pk
        )
        if (
            not self.country_code
            and self.category_id
            and self.category.country_code == GLOBAL_COUNTRY_CODE
            and not manual_source
        ):
            self.country_code = GLOBAL_COUNTRY_CODE
            if kwargs.get('update_fields') is not None:
                kwargs['update_fields'] = {
                    *kwargs['update_fields'], 'country_code',
                }
        self._normalize_code()
        self._validate_code_change()
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and "code" in update_fields:
            kwargs["update_fields"] = {*update_fields, "display_code"}
        super().save(*args, **kwargs)

    @property
    def used_count(self):
        return self.sql_used_count
