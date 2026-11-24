"""Storage configuration for organization data files."""

import posixpath
from datetime import datetime

from django.conf import settings
from django.core.files.storage import storages


def data_file_storage():
    """Return the configured Django storage for organization data files."""
    alias = getattr(settings, 'ORGANIZATIONATLAS_DATA_FILE_STORAGE', 'default')
    return storages[alias]


def data_file_upload_to(instance, filename):
    """Return the configured upload path for an organization data file."""
    upload_to = getattr(
        settings,
        'ORGANIZATIONATLAS_DATA_FILE_UPLOAD_TO',
        'organizationatlas/data/%Y/%m/',
    )
    if callable(upload_to):
        return upload_to(instance, filename)
    return posixpath.join(datetime.now().strftime(upload_to), filename)
