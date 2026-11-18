"""
apps/dashboard/services.py
==========================
Le tableau de bord de la v1 n'existait pas : le frontend avait besoin
d'un endpoint de statistiques et d'un endpoint d'activites (/activites/)
qui n'existaient pas cote serveur. Les KPIs etaient calcules dans le
navigateur a partir de listes completes (pigeons, cages, sorties) :
lent et impossible a mettre en cache.

Cette couche de service calcule TOUT en quelques requetes SQL
agregees (Count / Sum / TruncMonth), scopees sur le proprietaire.
"""

from datetime import timedelta

from django.db.models import Q, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone

from apps.cages.models import Cage, Occupation
from apps.couples.models import Couple
from apps.pigeons.models import Pigeon
from apps.reproductions.models import Reproduction
from apps.sales.models import Sortie

DUREE_INCUBATION = 18
DUREE_SEVRAGE = 30

LABELS_MOIS = [
    'Janv.', 'Fevr.', 'Mars', 'Avr.', 'Mai', 'Juin',
    'Juil.', 'Aout', 'Sept.', 'Oct.', 'Nov.', 'Dec.',
]


def _mois_suivants(mois_reference, nb=12):
    """Retourne [(cle 'YYYY-MM', label court), ...] sur N mois glissants."""
    mois_liste = []
    annee, mois = mois_reference.year, mois_reference.month
    for _ in range(nb):
        mois_liste.append((f'{annee:04d}-{mois:02d}', LABELS_MOIS[mois - 1]))
        mois -= 1
        if mois == 0:
            mois = 12
            annee -= 1
    return list(reversed(mois_liste))


def _serie_mensuelle(queryset, champ_date, champ_valeur, mois_reference):
    """Serie mensuelle agregee en SQL sur 12 mois glissants."""
    debut = mois_reference.replace(day=1) - timedelta(days=330)
    agg = (
        queryset.filter(**{f'{champ_date}__gte': debut})
        .annotate(_mois=TruncMonth(champ_date))
        .values('_mois')
        .annotate(total=Sum(champ_valeur))
    )
    par_mois = {row['_mois'].strftime('%Y-%m'): row['total'] or 0 for row in agg}
    return [
        {'mois': cle, 'label': label, 'total': par_mois.get(cle, 0)}
        for cle, label in _mois_suivants(mois_reference)
    ]


def _info_colombier(user):
    """
    Infos du colombier de l'utilisateur.
    Compatible avec les deux modeles possibles :
      - OneToOneField(related_name='colombier') -> user.colombier est un OBJET
        (cas du projet reel, voir apps/colombier/models.py)
      - ForeignKey(related_name='colombier')   -> user.colombier est un MANAGER
    Note : si le colombier n'existe pas, user.colombier leve
    RelatedObjectDoesNotExist (sous-classe d'AttributeError) : getattr
    avec default le gere proprement.
    """
    relation = getattr(user, 'colombier', None)
    if relation is not None and hasattr(relation, 'all'):
        relation = relation.first()
    if relation is None:
        return {'nom': 'Mon colombier', 'pays': '', 'ville': ''}
    return {
        'nom': relation.nom or 'Mon colombier',
        'pays': relation.pays or '',
        'ville': relation.ville or '',
    }


def build_dashboard_stats(user):
    """Construit l'objet DashboardStats complet pour l'utilisateur."""
    today = timezone.localdate()
    debut_mois = today.replace(day=1)
    debut_annee = today.replace(month=1, day=1)
    il_y_a_30j = today - timedelta(days=30)

    # ------------------------------------------------------------------
    # EFFECTIF
    # ------------------------------------------------------------------
    pigeons = Pigeon.objects.filter(owner=user, deleted_at__isnull=True)
    actifs = pigeons.filter(statut='actif')
    par_statut = {
        statut: pigeons.filter(statut=statut).count()
        for statut in ('actif', 'vendu', 'mort', 'perdu')
    }

    # ------------------------------------------------------------------
    # CAGES
    # ------------------------------------------------------------------
    cages = Cage.objects.filter(owner=user, est_active=True)
    occupations_actives = Occupation.objects.filter(
        cage__owner=user, date_fin__isnull=True,
    )
    cages_total = cages.count()
    cages_occupees = occupations_actives.values('cage').distinct().count()
    couples_en_cage = (
        occupations_actives.filter(type_occupation='couple')
        .values('cage').distinct().count()
    )

    # ------------------------------------------------------------------
    # REPRODUCTION
    # ------------------------------------------------------------------
    repros = Reproduction.objects.filter(couple__owner=user)
    # Dans ce projet, date_eclosion (obligatoire) est la date PREVUE
    # d'eclosion : une couvee est "en incubation" tant que cette date
    # n'est pas passee.
    incubations = repros.filter(date_eclosion__gte=today)
    eclosions_prevues_7j = incubations.filter(
        date_eclosion__lte=today + timedelta(days=7),
    ).count()
    repros_annee = repros.filter(date_ponte__year=today.year)
    jeunes_annee = repros_annee.aggregate(total=Sum('nombre_jeunes'))['total'] or 0
    oeufs_annee = repros_annee.aggregate(total=Sum('nombre_oeufs'))['total'] or 0
    taux_eclosion = round(jeunes_annee / oeufs_annee * 100, 1) if oeufs_annee else 0.0
    # ------------------------------------------------------------------
    # FINANCES
    # ------------------------------------------------------------------
    ventes = Sortie.objects.filter(owner=user, type_sortie='vente')
    ventes_mois = ventes.filter(date_sortie__gte=debut_mois)
    revenus_mois = ventes_mois.aggregate(total=Sum('prix'))['total'] or 0
    revenus_annee = (
        ventes.filter(date_sortie__year=today.year)
        .aggregate(total=Sum('prix'))['total'] or 0
    )
    nb_ventes_mois = ventes_mois.count()
    prix_moyen = round(revenus_mois / nb_ventes_mois, 2) if nb_ventes_mois else 0.0

    # ------------------------------------------------------------------
    # SERIES MENSUELLES (12 mois glissants, 2 requetes SQL)
    # ------------------------------------------------------------------
    naissances_par_mois = _serie_mensuelle(
        repros.filter(nombre_jeunes__gt=0), 'date_ponte', 'nombre_jeunes', today,
    )
    revenus_par_mois = _serie_mensuelle(
        ventes, 'date_sortie', 'prix', today,
    )

    # ------------------------------------------------------------------
       # ------------------------------------------------------------------
    # ALERTES
    # ------------------------------------------------------------------
    alertes = []
    repros_lights = repros.select_related('couple', 'couple__male', 'couple__femelle')

    # Eclosion prevue dans 3 jours
    for repro in repros_lights.filter(
        date_eclosion=today + timedelta(days=3),
        nombre_jeunes=0,
    ):
        alertes.append({
            'type': 'eclosion_imminente',
            'titre': 'Eclosion imminente',
            'description': (
                f'Eclosion attendue dans 3 jours pour le couple '
                f'{repro.couple.male.matricule} + {repro.couple.femelle.matricule}.'
            ),
            'date': str(repro.date_ponte),
            'reference_id': str(repro.id),
        })

   

    # Sevrage (30 jours apres eclosion) a preparer dans 3 jours
    for repro in repros_lights.filter(
        date_eclosion=today - timedelta(days=DUREE_SEVRAGE - 3),
        nombre_jeunes__gt=0,
    ):
        alertes.append({
            'type': 'sevrage_imminent',
            'titre': 'Sevrage a preparer',
            'description': (
                f'Sevrage dans 3 jours pour {repro.nombre_jeunes} jeune(s) du couple '
                f'{repro.couple.male.matricule} + {repro.couple.femelle.matricule}.'
            ),
            'date': str(repro.date_eclosion),
            'reference_id': str(repro.id),
        })

    for repro in repros_lights.filter(
        date_eclosion__isnull=False,
        date_eclosion=today - timedelta(days=DUREE_SEVRAGE - 3),
    ):
        alertes.append({
            'type': 'sevrage_imminent',
            'titre': 'Sevrage a preparer',
            'description': (
                f'Sevrage dans 3 jours pour {repro.nombre_jeunes} jeune(s) du couple '
                f'{repro.couple.male.matricule} + {repro.couple.femelle.matricule}.'
            ),
            'date': str(repro.date_eclosion),
            'reference_id': str(repro.id),
        })

    # ------------------------------------------------------------------
    # RESULTAT
    # ------------------------------------------------------------------
    return {
        'colombier': _info_colombier(user),
        'effectif': {
            'total': actifs.count(),
            'males': actifs.filter(sexe='M').count(),
            'femelles': actifs.filter(sexe='F').count(),
            'jeunes_30j': actifs.filter(date_naissance__gte=il_y_a_30j).count(),
            'par_statut': par_statut,
        },
        'cages': {
            'total': cages_total,
            'libres': max(cages_total - cages_occupees, 0),
            'occupees': cages_occupees,
            'couples': couples_en_cage,
        },
        'couples': {
            'actifs': Couple.objects.filter(
                owner=user, statut='actif',
            ).count(),
        },
        'reproduction': {
            'incubations_en_cours': incubations.count(),
            'eclosions_prevues_7j': eclosions_prevues_7j,
            'jeunes_annee': jeunes_annee,
            'taux_eclosion': taux_eclosion,
        },
        'finances': {
            'revenus_mois': float(revenus_mois),
            'revenus_annee': float(revenus_annee),
            'ventes_mois': nb_ventes_mois,
            'prix_moyen': prix_moyen,
        },
        'naissances_par_mois': naissances_par_mois,
        'revenus_par_mois': revenus_par_mois,
        'alertes': alertes,
    }


def build_recent_activities(user, limit=10, days=30):
    """
    Flux d'activite unifie (endpoint /activites/, consomme par
    useRecentActivity avec { count, results }).
    """
    depuis = timezone.now() - timedelta(days=days)
    evenements = []

    for pigeon in Pigeon.objects.filter(
        owner=user, deleted_at__isnull=True, created_at__gte=depuis,
    ):
        evenements.append({
            'id': f'pigeon-{pigeon.id}',
            'type': 'pigeon',
            'type_action': 'creation',
            'titre': 'Nouveau pigeon enregistre',
            'description': f'{pigeon.matricule} - {pigeon.get_sexe_display()} ({pigeon.race})',
            'date': pigeon.created_at,
            'badge': 'Pigeon',
            'utilisateur': user.username,
            'metadata': {'pigeon_id': str(pigeon.id), 'matricule': pigeon.matricule,
                         'sexe': pigeon.sexe},
        })

    for couple in Couple.objects.filter(owner=user, created_at__gte=depuis):
        evenements.append({
            'id': f'couple-{couple.id}',
            'type': 'couple',
            'type_action': 'creation',
            'titre': 'Couple forme',
            'description': f'{couple.male.matricule} + {couple.femelle.matricule}',
            'date': couple.created_at,
            'badge': 'Couple',
            'utilisateur': user.username,
            'metadata': {'couple_id': str(couple.id)},
        })

    for repro in Reproduction.objects.filter(
        couple__owner=user, created_at__gte=depuis,
    ).select_related('couple__male', 'couple__femelle'):
        evenements.append({
            'id': f'repro-{repro.id}',
            'type': 'reproduction',
            'type_action': 'creation',
            'titre': 'Nouvelle ponte enregistree',
            'description': (
                f'{repro.nombre_oeufs} oeuf(s) - couple '
                f'{repro.couple.male.matricule} + {repro.couple.femelle.matricule}'
            ),
            'date': repro.created_at,
            'badge': 'Repro',
            'utilisateur': user.username,
            'metadata': {'couple_id': str(repro.couple.id)},
        })

    for sortie in Sortie.objects.filter(
        owner=user, created_at__gte=depuis,
    ).select_related('pigeon'):
        titres = {
            'vente': 'Vente enregistree',
            'deces': 'Deces constate',
            'perte': 'Perte constatee',
        }
        description = sortie.pigeon.matricule
        if sortie.type_sortie == 'vente' and sortie.prix:
            description += f' - {sortie.prix}'
        evenements.append({
            'id': f'sortie-{sortie.id}',
            'type': 'sortie',
            'type_action': sortie.type_sortie,
            'titre': titres.get(sortie.type_sortie, 'Sortie enregistree'),
            'description': description,
            'date': sortie.created_at,
            'badge': 'Sortie',
            'utilisateur': user.username,
            'metadata': {'pigeon_id': str(sortie.pigeon.id)},
        })

    for occupation in Occupation.objects.filter(
        cage__owner=user, date_debut__gte=depuis,
    ).select_related('cage', 'pigeon', 'couple', 'couple__male', 'couple__femelle'):
        if occupation.type_occupation == 'couple' and occupation.couple:
            titre = 'Couple installe en cage'
            detail = (
                f'Cage {occupation.cage.numero} : '
                f'{occupation.couple.male.matricule} + {occupation.couple.femelle.matricule}'
            )
        elif occupation.pigeon:
            titre = 'Pigeon installe en cage'
            detail = f'Cage {occupation.cage.numero} : {occupation.pigeon.matricule}'
        else:
            continue
        evenements.append({
            'id': f'cage-{occupation.id}',
            'type': 'cage',
            'type_action': 'occupation',
            'titre': titre,
            'description': detail,
            'date': occupation.date_debut,
            'badge': 'Cage',
            'utilisateur': user.username,
            'metadata': {'type_occupation': occupation.type_occupation},
        })

    evenements.sort(key=lambda e: e['date'], reverse=True)
    results = evenements[:limit]
    for e in results:
        e['date'] = e['date'].isoformat()
    return {'count': len(evenements), 'results': results}
