from virtualqueryset.managers import VirtualManager


class OrganizationAtlasReferenceFixtureManager(VirtualManager):
    """CSV files shipped in the reference fixture library."""

    def get_data(self):
        from ...services.reference import list_fixtures

        return list_fixtures()
