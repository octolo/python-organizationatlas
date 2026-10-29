from unittest.mock import MagicMock

import pytest

from organizationatlas.providers.europe.france.huwise import HuwiseProvider


def test_search_escapes_quoted_phrase():
    provider = HuwiseProvider()
    provider._call_api = MagicMock(return_value={"results": []})

    provider.search_organization('ACME") OR true OR search("\\')

    assert provider._call_api.call_args.args[0] == (
        'search("ACME\\") OR true OR search(\\"\\\\")'
    )


@pytest.mark.parametrize(
    ("code", "where"),
    [
        ("917432254", 'siren="917432254"'),
        ("91743225400014", 'siret="91743225400014"'),
        ("W123456789", 'identifiantassociationunitelegale="W123456789"'),
    ],
)
def test_search_by_reference_uses_identifier_field(code, where):
    provider = HuwiseProvider()
    provider._call_api = MagicMock(return_value={"results": [{"siren": "917432254"}]})

    assert provider.search_organization_by_reference(code) == {"siren": "917432254"}
    provider._call_api.assert_called_once_with(where)


def test_identifier_search_uses_reference_lookup():
    provider = HuwiseProvider()
    provider.search_organization_by_reference = MagicMock(
        return_value={"siret": "91743225400014"}
    )

    assert provider.search_organization("91743225400014") == [
        {"siret": "91743225400014"}
    ]
    provider.search_organization_by_reference.assert_called_once_with(
        "91743225400014",
        raw=False,
    )
