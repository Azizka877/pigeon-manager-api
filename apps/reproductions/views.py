"""
apps/reproductions/views.py (v2)
================================
Corrections :
1. SECURITY - scoping proprietaire via le couple (la Reproduction herite
   aussi d'OwnedModel : double verrou).
2. ACTION ajouter_jeunes - le frontend appelle POST /reproductions/{id}/
   ajouter_jeunes/ avec { jeunes: [{matricule, sexe, couleur, race}] }.
   Endpoint serveur qui cree les jeunes Pigeons, les rattache au couple
   (pere/mere) et met a jour nombre_jeunes - tout en une transaction.
"""

from django.db import transaction
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.ownership import OwnerOnlyPermission, OwnerQuerysetMixin
from apps.pigeons.models import Pigeon
from apps.pigeons.serializers import PigeonMiniSerializer

from .models import Reproduction
from .serializers import ReproductionSerializer


class ReproductionViewSet(OwnerQuerysetMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, OwnerOnlyPermission]
    serializer_class = ReproductionSerializer
    queryset = Reproduction.objects.all()
    filterset_fields = ['couple', 'date_ponte']

    def get_queryset(self):
        return (
            super().get_queryset()
            .select_related('couple', 'couple__male', 'couple__femelle')
            .prefetch_related('jeunes')
        )

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def ajouter_jeunes(self, request, pk=None):
        reproduction = self.get_object()
        jeunes_data = request.data.get('jeunes', [])
        if not isinstance(jeunes_data, list) or not jeunes_data:
            return Response(
                {'jeunes': 'Fournissez une liste non vide de jeunes.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        date_naissance = reproduction.date_eclosion or reproduction.date_ponte
        race_heritee = reproduction.couple.male.race if reproduction.couple.male else None

        crees = []
        for jeune in jeunes_data:
            matricule = (jeune.get('matricule') or '').strip()
            sexe = jeune.get('sexe')
            if not matricule or sexe not in ('M', 'F'):
                return Response(
                    {'jeunes': 'Chaque jeune requiert un matricule et un sexe M ou F.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if Pigeon.objects.filter(
                matricule=matricule, owner=request.user, deleted_at__isnull=True,
            ).exists():
                return Response(
                    {'jeunes': f'Le matricule {matricule} existe deja dans votre colombier.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            pigeon = Pigeon.objects.create(
                owner=request.user,
                matricule=matricule,
                sexe=sexe,
                race=jeune.get('race') or race_heritee or 'Voyageur',
                date_naissance=date_naissance,
                couleur=jeune.get('couleur') or None,
                pere=reproduction.couple.male,
                mere=reproduction.couple.femelle,
                statut='actif',
            )
            reproduction.jeunes.add(pigeon)
            crees.append(pigeon)

        reproduction.nombre_jeunes = reproduction.jeunes.count()
        reproduction.save()

        return Response({
            'message': f'{len(crees)} jeune(s) ajoute(s) a la couvee.',
            'jeunes': PigeonMiniSerializer(crees, many=True).data,
        }, status=status.HTTP_201_CREATED)
