"""Django OrganizationAtlas - Organization information management."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("django-organizationatlas")
except PackageNotFoundError:
    __version__ = "0.0.0.dev"

__all__ = []
