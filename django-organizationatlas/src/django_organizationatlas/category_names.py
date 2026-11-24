"""Names of built-in categories associated with external data keys."""

from django.db.models import Case, CharField, F, Value, When

CATEGORY_NAMES = {
    'apitrace': 'API trace',
    'visual_identity': 'Visual identity',
    'gender': 'Gender',
    'gender_response': 'Gender disclosure',
    'gender_structure': 'Ownership structure',
    'organization_relation': 'Organization relation',
    'organization_type': 'Organization type',
    'slice_effective': 'Employee headcount bracket',
    'stakeholder_relation': 'Stakeholder relation',
    'LEGAL': 'Legal',
    'STATUTES': 'Statutes',
    'GOVERNANCE': 'Governance',
    'DECISIONS': 'Decisions',
    'CONTRACTS': 'Contracts',
    'LAW': 'Law',
    'ARTICLES': 'Articles of association',
    'SHAREHOLDERS_AGREEMENT': 'Shareholders agreement',
    'CONTRACT': 'Contract',
    'CORPORATE_DECISION': 'Corporate decision',
    'INTERNAL_POLICY': 'Internal policy',
    'OTHER': 'Other',
    'UNKNOWN': 'Unknown',
    'ape': 'APE code',
    'category': 'Company category',
    'legalform': 'Legal form',
    'profil_capitalisation': 'Capitalization profile',
    'qualite_detenteur': 'Holder status',
    'regime_reglementaire': 'Regulatory regime',
}
DATA_TYPE_NAMES = {name: key for key, name in CATEGORY_NAMES.items()}


def category_name(data_type):
    """Resolve a provider data key to its built-in category name."""
    return CATEGORY_NAMES.get(data_type, data_type)


def data_type_name(category):
    """Resolve a built-in category name to its provider data key."""
    return DATA_TYPE_NAMES.get(category, category)


def category_name_expression(field):
    """Resolve data keys in a queryset without changing their stored value."""
    return Case(
        *(
            When(**{field: key}, then=Value(name))
            for key, name in CATEGORY_NAMES.items()
        ),
        default=F(field),
        output_field=CharField(),
    )
