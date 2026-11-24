"""Built-in references for organization visual identity."""

VISUAL_IDENTITY_CATEGORY = 'Visual identity'
VISUAL_IDENTITY_TYPES = {
    'LOGO': 'image',
    'FAVICON': 'image',
    'FONT': 'file',
    'PRIMARY_COLOR': 'str',
    'SECONDARY_COLOR': 'str',
}
def visual_identity_data_type(reference):
    """Return the data key and value type for a visual identity reference."""
    if reference.category.name != VISUAL_IDENTITY_CATEGORY:
        return None
    value_type = VISUAL_IDENTITY_TYPES.get(reference.code)
    if value_type is None:
        return None
    return f'visual_identity_{reference.code.lower()}', value_type
