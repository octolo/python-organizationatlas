"""Normalization of reference codes."""


def normalize_reference_code(value: str) -> str:
    """Return the comparison form of a reference code."""
    return value.strip().replace('.', '').upper()
