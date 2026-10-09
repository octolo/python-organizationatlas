from django.db import models
from django.utils.translation import gettext_lazy as _

from ..managers.reference import (
    OrganizationAtlasReferenceCategoryManager,
    OrganizationAtlasReferenceManager,
)
from .source import OrganizationAtlasSourceBase


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

    @classmethod
    def for_name(cls, name: str, country_code: str):
        category, _created = cls.objects.get_or_create(
            name=name,
            country_code=country_code,
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
    code = models.CharField(
        max_length=255,
        verbose_name=_("Code"),
        help_text=_("Reference code"),
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

    objects = OrganizationAtlasReferenceManager()

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

    def __str__(self):
        return f"{self.code} - {self.description}"

    @property
    def used_count(self):
        return self.sql_used_count
