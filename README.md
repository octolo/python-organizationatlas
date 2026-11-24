# OrganizationAtlas

Monorepo contenant **organizationatlas** (bibliothèque Python pour la recherche d'entreprises) et **django-organizationatlas** (intégration Django).

## Packages

### organizationatlas — `python-organizationatlas/`

Bibliothèque Python pour la recherche et l'enrichissement d'informations entreprises. Interface unifiée vers plusieurs fournisseurs de données (Pappers, societe.com, etc.) via ProviderKit.

- **Recherche d'entreprises** : par nom, domaine ou identifiant
- **Enrichissement** : documents, événements, dirigeants, UBO
- **Format normalisé** : structure de champs cohérente entre les providers

📁 Docs : [python-organizationatlas/docs/](python-organizationatlas/docs/)

### django-organizationatlas — `django-organizationatlas/`

Intégration Django pour OrganizationAtlas. Champs, widgets, admin.

📁 Docs : [django-organizationatlas/docs/](django-organizationatlas/docs/)

## Structure du dépôt

```
organizationatlas/
├── python-organizationatlas/   # Bibliothèque core
├── django-organizationatlas/    # Intégration Django
└── README.md
```

## Développement

La CI vérifie aussi les dépendances et exécute Bandit séparément pour les
paquets Python et Django.

Chaque package a son propre `service.py` :

```bash
# Dans python-organizationatlas/ ou django-organizationatlas/
./service.py dev install-dev
./service.py dev test
./service.py quality lint
```

## Licence

MIT

## Local audit

Install the project's development/test dependencies (including both local
packages where applicable), plus the audit tools:

```bash
python -m pip install ruff mypy bandit pip-audit vulture radon xenon pytest pytest-django pytest-cov build twine
make audit
```

Use the activated environment's Python, or pass `make audit PYTHON=/path/to/python`.
On systems without Make, run `python scripts/audit.py` directly. Git is required;
the geoaddress widget tests also require Node.js. The audit reports missing test
suites and runs all available checks even when earlier checks fail.
Xenon checks the absolute C, module B, and average A complexity thresholds. Existing
lint, typing, security, dependency, or test findings can make the audit fail.
CI also runs this audit as a non-blocking job and separately reports Radon maintainability without imposing a threshold.
