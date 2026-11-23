"""
apps/pigeons/pedigree_views.py
==============================
Deux vues API autonomes (aucune modification des vues existantes) :

1. GET /api/pigeons/{id}/pedigree/
   -> PDF officiel imprimable (arbre 4 générations + QR de partage).
      Accès : JWT du propriétaire OU jeton de partage signé (?t=...)
      imprimé dans le QR code du PDF lui-même.

2. POST /api/genetique/simulation/
   -> Simulation de consanguinité : COI exact du descendant prévu d'un
      couple (moteur apps.core.coi, méthode tabulaire de Wright) +
      détail des ancêtres communs et recommandation d'élevage.

Les deux routes sont enregistrées dans backend/urls.py (racine), à côté
des includes d'applications — les fichiers d'urls des apps restent
intacts.
"""

import re
from datetime import date

from django.core import signing
from django.http import HttpResponse
from django.urls import reverse
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.colombier.models import ColombierConfig
from apps.core.coi import (
    MAX_GENERATIONS,
    analyser_croisement,
    classifier,
    consanguinite,
    en_pourcent,
)
from apps.core.pedigree_pdf import generer_pdf

from .models import Pigeon
from .serializers import PigeonMiniSerializer

# Sel de signature des liens de partage publics : les jetons restent
# valables indéfiniment, comme un pedigree papier — révocation possible
# en changeant le sel (redéploiement).
SEL_PARTAGE = 'pigeonmanager.pedigree.v1'


def _nom_fichier(matricule):
    propre = re.sub(r'[^A-Za-z0-9_-]+', '-', str(matricule or 'pigeon'))
    return f"pedigree-{propre.strip('-') or 'pigeon'}.pdf"


def _construire_arbre(pigeon, profondeur):
    """Arbre imbriqué 4 générations (None = inconnu), même format que
    l'action `arbre` existante."""
    if pigeon is None or profondeur < 0:
        return None
    return {
        'matricule': pigeon.matricule,
        'sexe': pigeon.sexe,
        'race': pigeon.race,
        'annee': pigeon.date_naissance.year if pigeon.date_naissance else None,
        'pere': _construire_arbre(pigeon.pere, profondeur - 1),
        'mere': _construire_arbre(pigeon.mere, profondeur - 1),
    }


class PedigreePDFView(APIView):
    """
    GET /api/pigeons/{id}/pedigree/?t=<jeton facultatif>

    Authentifié (JWT) + propriétaire du pigeon : PDF généré avec un
    jeton de partage intégré au QR.
    Anonyme : accepté uniquement avec un jeton `t` valide (lien imprimé
    sur le pedigree, partageable sans compte).
    """
    permission_classes = [AllowAny]

    def get(self, request, pk):
        pk_str = str(pk)
        pigeon = None

        if request.user and request.user.is_authenticated:
            pigeon = Pigeon.objects.filter(
                id=pk, owner=request.user, deleted_at__isnull=True,
            ).first()

        jeton_valide = False
        if pigeon is None:
            jeton = request.query_params.get('t', '')
            if jeton:
                try:
                    charge = signing.loads(jeton, salt=SEL_PARTAGE)
                    jeton_valide = (charge.get('p') == pk_str)
                except (signing.BadSignature, KeyError, ValueError):
                    jeton_valide = False
            if jeton_valide:
                pigeon = Pigeon.objects.filter(
                    id=pk, deleted_at__isnull=True,
                ).first()

        if pigeon is None:
            if request.user and request.user.is_authenticated:
                # Connecté mais pas propriétaire : 404, pour ne pas
                # révéler l'existence du pigeon (convention du projet).
                return Response(
                    {'detail': "Pigeon introuvable dans votre colombier."},
                    status=404,
                )
            return Response(
                {'detail': (
                    "Accès refusé : connectez-vous, ou ouvrez le lien de "
                    "partage imprimé sous le QR du pedigree."
                )},
                status=401,
            )

        # Jeton de partage (signé) intégré au QR du document
        jeton_partage = signing.dumps({'p': pk_str}, salt=SEL_PARTAGE)
        try:
            base = reverse('pedigree-pdf', args=[pk_str])
        except Exception:
            base = request.path
        url_public = request.build_absolute_uri(base) + f'?t={jeton_partage}'

        # QR code (image PIL)
        try:
            import qrcode
            qr_image = qrcode.make(url_public, box_size=10, border=2).convert('RGB')
        except Exception:
            qr_image = None

        colombier = None
        if pigeon.owner is not None:
            colombier = (
                ColombierConfig.objects
                .filter(proprietaire=pigeon.owner)
                .first()
            )

        coi = consanguinite(pigeon)
        niveau = classifier(coi) if (pigeon.pere and pigeon.mere) else {
            'niveau_label': 'Non calculable',
            'couleur': '#9ca3af',
        }

        pdf = generer_pdf({
            'colombier': colombier.nom if colombier else 'PigeonManager',
            'genere_le': date.today().strftime('%d/%m/%Y'),
            'pigeon': {
                'matricule': pigeon.matricule,
                'sexe': pigeon.sexe,
                'race': pigeon.race,
                'couleur': pigeon.couleur,
                'date_naissance': pigeon.date_naissance,
            },
            'coi': coi if (pigeon.pere and pigeon.mere) else None,
            'niveau_label': niveau['niveau_label'],
            'couleur_niveau': niveau['couleur'],
            'arbre': _construire_arbre(pigeon, 3),
            'qr_image': qr_image,
            'profondeur': MAX_GENERATIONS,
        })

        reponse = HttpResponse(pdf, content_type='application/pdf')
        reponse['Content-Disposition'] = (
            f'attachment; filename="{_nom_fichier(pigeon.matricule)}"'
        )
        return reponse


class SimulationCoupleView(APIView):
    """
    POST /api/genetique/simulation/
    Body : {"male_id": "<uuid>", "femelle_id": "<uuid>"}

    Renvoie le COI exact du descendant prévu, le détail des ancêtres
    communs (parts qui somment au COI) et une recommandation d'élevage.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        male_id = request.data.get('male_id') or request.data.get('male')
        femelle_id = (
            request.data.get('femelle_id') or request.data.get('femelle')
        )
        if not male_id or not femelle_id:
            return Response(
                {'detail': "Champs requis : 'male_id' et 'femelle_id'."},
                status=400,
            )

        male = Pigeon.objects.filter(
            id=male_id, owner=request.user, deleted_at__isnull=True,
        ).first()
        femelle = Pigeon.objects.filter(
            id=femelle_id, owner=request.user, deleted_at__isnull=True,
        ).first()
        manquants = []
        if male is None:
            manquants.append('male_id')
        if femelle is None:
            manquants.append('femelle_id')
        if manquants:
            return Response(
                {'detail': "Pigeon introuvable dans votre colombier.",
                 'champs': manquants},
                status=404,
            )

        if male.sexe != 'M' or femelle.sexe != 'F':
            return Response(
                {'detail': (
                    "Le mâle doit être un pigeon de sexe M et la femelle "
                    "de sexe F."
                )},
                status=400,
            )

        analyse = analyser_croisement(male, femelle)
        niveau = classifier(analyse['coi'])

        def fiche(pigeon, coi):
            donnees = PigeonMiniSerializer(pigeon).data
            donnees['coi'] = coi
            return donnees

        ancetres = []
        for ancetre in analyse['ancetres_communs']:
            ancetres.append({
                'id': ancetre['id'],
                'matricule': ancetre['matricule'],
                'sexe': ancetre['sexe'],
                'race': ancetre['race'],
                'contribution': ancetre['contribution'],
                'contribution_pourcent': en_pourcent(ancetre['contribution']),
                'gen_male': ancetre['gen_male'],
                'gen_femelle': ancetre['gen_femelle'],
                'coi_ancetre': ancetre['coi_ancetre'],
            })

        return Response({
            'male': fiche(male, consanguinite(male)),
            'femelle': fiche(femelle, consanguinite(femelle)),
            'descendant': {
                'coi': analyse['coi'],
                'coi_pourcent': en_pourcent(analyse['coi']),
                **niveau,
            },
            'ancetres_communs': ancetres,
            'profondeur_analyse': analyse['profondeur_analyse'],
        })


class CoiPigeonView(APIView):
    """
    GET /api/pigeons/{id}/coi/
    -> COI du pigeon lui-meme (methode de Wright) + niveau.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        pigeon = Pigeon.objects.filter(
            id=pk, owner=request.user, deleted_at__isnull=True,
        ).first()
        if pigeon is None:
            return Response(
                {'detail': "Pigeon introuvable dans votre colombier."},
                status=404,
            )
        parents_connus = bool(pigeon.pere and pigeon.mere)
        coi = consanguinite(pigeon)
        if parents_connus:
            niveau = classifier(coi)
        else:
            niveau = {'niveau_label': 'Non calculable', 'couleur': '#9ca3af'}
        return Response({
            'id': str(pigeon.id),
            'matricule': pigeon.matricule,
            'coi': coi,
            'coi_pourcent': en_pourcent(coi),
            'niveau_label': niveau['niveau_label'],
            'couleur': niveau['couleur'],
            'parents_connus': parents_connus,
        })
