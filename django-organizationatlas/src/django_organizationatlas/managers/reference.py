from django.db import models
from django.db.models import Count


class OrganizationAtlasReferenceQuerySet(models.QuerySet):
    def with_usage_count(self):
        return self.annotate(sql_used_count=Count("to_organizationatlasdata"))


class OrganizationAtlasReferenceManager(models.Manager):
    def get_queryset(self):
        return OrganizationAtlasReferenceQuerySet(self.model, using=self._db)
