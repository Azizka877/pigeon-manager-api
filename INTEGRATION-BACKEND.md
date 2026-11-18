# Guide d'integration - Backend Django

Corrections de securite, d'integrite et de performance du backend PigeonManager.
Chaque fichier remplace (ou enrichit) le fichier du meme nom dans votre projet.

---

## 1. Arborescence livree

```
backend/
├── apps/core/ownership.py          # NOUVEAU - isolation multi-tenant
├── apps/dashboard/                 # NOUVELLE APP - stats + activites
│   ├── apps.py
│   ├── serializers.py
│   ├── services.py                 # calcul des KPIs (SQL agrege)
│   ├── views.py                    # /api/dashboard/stats/ + /api/activites/
│   └── urls.py
├── apps/cages/views.py             # occuper / liberer / historique (serveur)
├── apps/cages/serializers.py       # + HistoriqueItemSerializer, prefetch
├── apps/pigeons/views.py           # soft delete + filtres + genealogie
├── apps/pigeons/serializers.py     # + PigeonMiniSerializer + unicite par owner
├── apps/couples/views.py           # action rompre (cage liberee cote serveur)
├── apps/couples/serializers.py     # anti-couple-multiple + sexes verifies
├── apps/reproductions/views.py     # action ajouter_jeunes (creation des jeunes)
├── apps/reproductions/serializers.py  # statut calcule + couple_details + dates
├── apps/sales/views.py             # logique metier atomique + annulation
├── apps/sales/services.py          # traiter_sortie / annuler_sortie
└── apps/sales/serializers.py       # champs conditionnels validates
```

## 2. Etape 1 - Faire heriter les modeles d'OwnedModel

Dans `apps/pigeons/models.py`, `apps/cages/models.py`, `apps/couples/models.py`,
`apps/reproductions/models.py`, `apps/sales/models.py` :

```python
from apps.core.ownership import OwnedModel

class Pigeon(OwnedModel):          # au lieu de models.Model
    ...
```

Le modele abstrait ajoute automatiquement `owner = FK(User)` a chaque table.

> Important : supprimez le `unique=True` du champ `Pigeon.matricule` et remplacez-le
> par une contrainte par proprietaire dans `Meta.constraints` :
>
> ```python
> from django.db.models import UniqueConstraint
> constraints = [
>     UniqueConstraint(fields=['owner', 'matricule'], name='uniq_matricule_par_owner')
> ]
> ```

## 3. Etape 2 - Migrations et backfill

```bash
python manage.py makemigrations pigeons cages couples reproductions sales
python manage.py migrate
```

Les donnees existantes auront `owner = NULL`. Deux options :

- **Mono-eleveur aujourd'hui** : rattacher manuellement
  ```bash
  python manage.py shell -c "from apps.pigeons.models import Pigeon; \
      from django.contrib.auth.models import User; \
      admin = User.objects.get(username='admin'); \
      Pigeon.objects.update(owner=admin)"
  ```
  (idem pour Cage, Couple, Reproduction, Sortie)
- **Multi-eleveurs** : rattacher avant toute mise en production, puis passer
  `null=False` sur le champ `owner` dans une deuxieme migration.

## 4. Etape 3 - Enregistrer la nouvelle app

Dans `settings.py` :

```python
INSTALLED_APPS = [
    ...
    'apps.dashboard',       # NOUVEAU
    'apps.core',            # NOUVEAU (pas de modeles, mais propre pour les tests)
    ...
]
```

## 5. Etape 4 - Brancher les routes

Dans `backend/urls.py` :

```python
path('api/', include('apps.dashboard.urls')),   # /api/dashboard/stats/ + /api/activites/
```

## 6. Etape 5 - Durcissement (recommande)

1. **Throttling sur les endpoints d'auth** (brute force) :

```python
REST_FRAMEWORK = {
    ...
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '60/min',
    },
}
```
et dans `apps/users/views.py`, ajoutez un throttle plus strict sur le login :
`throttle_scope` ou `AnonRateThrottle` cible `5/min`.

2. **Swagger** : proteger le schema en production
   (`permission_classes=(permissions.IsAdminUser,)` dans `urls.py`).

3. **JWT** : activer la rotation
   (`'ROTATE_REFRESH_TOKENS': True` - le `BLACKLIST_AFTER_ROTATION` de la v1
   etait sans effet sans rotation ; ajouter aussi
   `'rest_framework_simplejwt.token_blacklist'` a INSTALLED_APPS).

4. **settings.py** : si Django >= 4.2, remplacer
   `STATICFILES_STORAGE = 'whitenoise.storage...'` par :

```python
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
    },
}
```

5. **Migration SQLite -> Postgres uniquement** : le fallback SQLite de la v1
   risque d'etre utilise accidentellement si DATABASE_URL manque. Ajoutez :

```python
if not DATABASE_URL and not DEBUG:
    raise ValueError("DATABASE_URL est requis en production")
```

## 7. Changements de contrat API - impact frontend

| Endpoint | Avant | Apres | Impact front |
|---|---|---|---|
| `/cages/{id}/occuper/` | absent (404) | POST valide et cree l'occupation | aucun (deja appele) |
| `/cages/{id}/liberer/` | absent (404) | DELETE clot l'occupation | aucun (deja appele) |
| `/cages/{id}/historique/` | absent (404) | GET journal des occupations | aucun (deja appele) |
| `/activites/` | absent (404) | GET `{count, results}` | aucun (deja appele) |
| `/couples/{id}/rompre/` | PATCH + logique client | POST atomique serveur | remplacer `useSeparateCouple` |
| `/sorties/` POST | statut+ cage modifie cote client | effets 100 % serveur | simplifier `useCreateSortie` |
| `/pigeons/` DELETE | DELETE SQL definitif | soft delete (`deleted_at`) | aucun |
| `/reproductions/{id}/ajouter_jeunes/` | absent | POST avec creation des jeunes | aucun (deja appele) |

## 8. Recommandations de modele (evolutions suggerees)

- `Couple.date_formation = auto_now_add=True` : rendre le champ editable
  (`models.DateField(default=timezone.localdate)`) pour pouvoir re-former un
  couple a une date historique.
- `Reproduction` : ajouter les champs persistants `statut` et `nombre_eclos`
  si vous souhaitez les filtrer en base (le serializer les calcule deja).
- `Occupation` : ajouter un index `models.Index(fields=['date_fin'])` pour
  accelerer le scoping des occupations actives.
