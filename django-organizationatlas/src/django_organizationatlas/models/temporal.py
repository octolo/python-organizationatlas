"""Temporal validity mixin for fact-like models (bitemporal: valid-time vs the
transaction-time already provided by OrganizationAtlasSourceBase)."""

from datetime import date

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

ORGANIZATIONATLAS_FIELDS_TEMPORAL = ["valid_from", "valid_to"]


class TemporalValidityMixin(models.Model):
    """Adds a real-world validity period (depuis / jusqu'au) to a record.

    A record with ``valid_to = None`` is the *current* (open) version. History is
    kept by closing the old version (setting ``valid_to``) and inserting a new one.

    Concrete models may set ``temporal_key_fields`` to enforce "only one open
    record per logical key" — both at the DB level (declare a partial
    ``UniqueConstraint(... condition=Q(valid_to__isnull=True))``) and at the
    validation level via ``clean()``.
    """

    # Logical key used to enforce a single open (current) record. Empty = no check.
    temporal_key_fields: tuple[str, ...] = ()

    valid_from = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Valid from"),
        help_text=_("Date from which the information is valid (depuis)"),
    )
    valid_to = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Valid to"),
        help_text=_("Date until which the information was valid (jusqu'au, empty = still current)"),
    )

    class Meta:
        abstract = True

    @property
    def is_current(self) -> bool:
        return self.valid_to is None or self.valid_to >= date.today()

    def _temporal_key(self) -> dict:
        key = {}
        for name in self.temporal_key_fields:
            attname = f"{name}_id" if hasattr(self, f"{name}_id") else name
            key[attname] = getattr(self, attname)
        return key

    def _validate_single_open_record(self):
        if self.valid_to is not None or not self.temporal_key_fields:
            return
        qs = type(self)._base_manager.filter(valid_to__isnull=True, **self._temporal_key())
        if self.pk:
            qs = qs.exclude(pk=self.pk)
        if qs.exists():
            raise ValidationError(
                _(
                    "An open record already exists for this key. Close it "
                    "(set 'Valid to') before inserting a new version."
                )
            )

    def clean(self):
        super().clean()
        if self.valid_from and self.valid_to and self.valid_to < self.valid_from:
            raise ValidationError(
                {"valid_to": _("'Valid to' cannot be earlier than 'Valid from'.")}
            )
        self._validate_single_open_record()
