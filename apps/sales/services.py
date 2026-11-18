"""
apps/sales/services.py (v2)
===========================
LOGIQUE METIER COTE SERVEUR.

Probleme corrige :
    Dans la v1, c'est le FRONTEND (hook useCreateSortie) qui, apres avoir
    cree la sortie : cherchait toutes les cages, trouvait celle du pigeon,
    verifiait le statut de l'autre pigeon du couple puis liberait la cage
    via une 2e requete. Trois problemes : (1) la logique peut etre
    interrompue (onglet ferme, bug reseau) et la donnee devient
    incoherente ; (2) elle est falsifiable ; (3) elle fait des dizaines de
    requetes depuis le navigateur.

Solution : une fonction de service transactionnelle, appelee par le
ViewSet a la creation de la sortie. Le statut du pigeon est mis a jour et
la cage est liberee automatiquement si necessaire.
"""

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.cages.models import Occupation

STATUT_PAR_TYPE = {
    'vente': 'vendu',
    'deces': 'mort',
    'perte': 'perdu',
}


@transaction.atomic
def traiter_sortie(sortie):
    """
    Applique les effets d'une sortie :
      1. met a jour le statut du pigeon (vendu / mort / perdu),
      2. libere sa cage si elle devient inutile,
      3. verifie la coherence du couple si le pigeon en faisait partie.
    Retourne le dictionnaire des effets appliques (pour journalisation).
    """
    pigeon = sortie.pigeon
    effets = {'statut_precedent': pigeon.statut, 'cage_liberee': None}

    # 1. Statut du pigeon
    pigeon.statut = STATUT_PAR_TYPE[sortie.type_sortie]
    pigeon.save(update_fields=['statut', 'updated_at'])

    # 2. Cage du pigeon (seul OU membre d'un couple)
    occupation = (
        Occupation.objects
        .filter(date_fin__isnull=True)
        .filter(
            Q(pigeon=pigeon) | Q(couple__male=pigeon) | Q(couple__femelle=pigeon)
        )
        .select_related('cage', 'couple', 'couple__male', 'couple__femelle')
        .first()
    )

    if occupation is None:
        return effets

    if occupation.type_occupation == 'seul':
        occupation.liberer()
        effets['cage_liberee'] = str(occupation.cage.numero)
        return effets

    # Couple : la cage n'est liberee que si l'autre membre n'est plus actif
    couple = occupation.couple
    autre = couple.femelle if couple.male_id == pigeon.id else couple.male
    autre_inactif = (
        autre is None
        or autre.statut != 'actif'
        or autre.deleted_at is not None
    )
    if autre_inactif:
        occupation.liberer()
        effets['cage_liberee'] = str(occupation.cage.numero)
        # Le couple n'a plus de raison d'etre actif : on le rompt.
        couple.statut = 'rompu'
        couple.date_rupture = sortie.date_sortie or timezone.localdate()
        couple.save(update_fields=['statut', 'date_rupture', 'updated_at'])

    return effets


@transaction.atomic
def annuler_sortie(sortie):
    """
    Retour arriere a la suppression d'une sortie : le pigeon redevient
    actif. (La cage reste libre : re-affectation manuelle, plus sur.)
    """
    pigeon = sortie.pigeon
    pigeon.statut = 'actif'
    pigeon.save(update_fields=['statut', 'updated_at'])
