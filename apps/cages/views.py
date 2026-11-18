from django.db import transaction
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.ownership import OwnerOnlyPermission, OwnerQuerysetMixin
from apps.couples.models import Couple
from apps.pigeons.models import Pigeon

from .models import Cage, Occupation
from .serializers import CageSerializer, HistoriqueItemSerializer, OccupationSerializer


class CageViewSet(OwnerQuerysetMixin, viewsets.ModelViewSet):
    """
    CRUD des cages + actions metier (occuper / liberer / historique).
    Toutes les donnees sont scoping sur le proprietaire connecte.
    """
    permission_classes = [IsAuthenticated, OwnerOnlyPermission]
    serializer_class = CageSerializer

    def get_queryset(self):
        base = super().get_queryset()
        return (
            base.filter(est_active=True)
            .prefetch_related(
                'occupations__pigeon',
                'occupations__couple__male',
                'occupations__couple__femelle',
            )
        )

    # ------------------------------------------------------------------
    # OCCUPER : affecte un pigeon seul ou un couple a une cage
    # ------------------------------------------------------------------
    @action(detail=True, methods=['post'])
    @transaction.atomic
    def occuper(self, request, pk=None):
        cage = self.get_object()

        if cage.occupation_actuelle is not None:
            return Response(
                {'detail': f'La cage {cage.numero} est deja occupee.'},
                status=status.HTTP_409_CONFLICT,
            )

        type_occupation = request.data.get('type_occupation')
        if type_occupation not in ('seul', 'couple'):
            return Response(
                {'type_occupation': "Choix invalides : 'seul' ou 'couple'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if type_occupation == 'seul':
            pigeon_id = request.data.get('pigeon_id')
            pigeon = (
                Pigeon.objects
                .filter(
                    id=pigeon_id,
                    owner=request.user,
                    statut='actif',
                    deleted_at__isnull=True,
                )
                .first()
            )
            if pigeon is None:
                return Response(
                    {'pigeon_id': 'Pigeon introuvable, inactif ou supprime.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            deja_en_cage = Occupation.objects.filter(
                pigeon=pigeon, date_fin__isnull=True,
            ).exists()
            if deja_en_cage:
                return Response(
                    {'pigeon_id': f'{pigeon.matricule} occupe deja une autre cage.'},
                    status=status.HTTP_409_CONFLICT,
                )
            occupation = Occupation.objects.create(
                cage=cage, pigeon=pigeon, type_occupation='seul',
            )
        else:  # couple
            couple_id = request.data.get('couple_id')
            couple = (
                Couple.objects
                .filter(id=couple_id, owner=request.user, statut='actif')
                .select_related('male', 'femelle')
                .first()
            )
            if couple is None:
                return Response(
                    {'couple_id': 'Couple introuvable ou deja rompu.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            deja_en_cage = Occupation.objects.filter(
                couple=couple, date_fin__isnull=True,
            ).exists()
            if deja_en_cage:
                return Response(
                    {'couple_id': 'Ce couple occupe deja une autre cage.'},
                    status=status.HTTP_409_CONFLICT,
                )
            occupation = Occupation.objects.create(
                cage=cage, couple=couple, type_occupation='couple',
            )

        serializer = OccupationSerializer(occupation)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    # ------------------------------------------------------------------
    # LIBERER : clot l'occupation en cours de la cage
    # ------------------------------------------------------------------
    @action(detail=True, methods=['delete'])
    def liberer(self, request, pk=None):
        cage = self.get_object()
        occupation = cage.occupation_actuelle
        if occupation is None:
            return Response(
                {'detail': f'La cage {cage.numero} est deja libre.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        occupation.liberer()
        return Response({'detail': f'La cage {cage.numero} est liberée.'})

    # ------------------------------------------------------------------
    # HISTORIQUE : journal des occupations (format attendu par le front)
    # ------------------------------------------------------------------
    @action(detail=True, methods=['get'])
    def historique(self, request, pk=None):
        cage = self.get_object()
        items = []
        occupations = list(
            cage.occupations
            .select_related('pigeon', 'couple', 'couple__male', 'couple__femelle')
            .order_by('-date_debut')
        )

        for occupation in occupations:
            if occupation.type_occupation == 'couple' and occupation.couple:
                matricules = (
                    f"{occupation.couple.male.matricule} + "
                    f"{occupation.couple.femelle.matricule}"
                )
                description = f'Couple {matricules} installe'
                metadata = {
                    'couple_id': str(occupation.couple.id),
                    'male': occupation.couple.male.matricule,
                    'femelle': occupation.couple.femelle.matricule,
                }
            elif occupation.pigeon:
                description = f'Pigeon {occupation.pigeon.matricule} affecte'
                metadata = {'pigeon_id': str(occupation.pigeon.id),
                            'matricule': occupation.pigeon.matricule}
            else:
                description = 'Occupation enregistree'
                metadata = {}

            items.append({
                'id': str(occupation.id),
                'type_action': 'occupation',
                'description': description,
                'date_action': occupation.date_debut,
                'date_formatee': timezone.localtime(occupation.date_debut).strftime(
                    '%d/%m/%Y a %H:%M'
                ),
                'utilisateur_nom': request.user.username,
                'metadata': metadata,
            })

            # Restituer aussi la liberation qui a cloture cette occupation
            if occupation.date_fin:
                items.append({
                    'id': str(occupation.id) + '-lib',
                    'type_action': 'liberation',
                    'description': 'Cage liberee',
                    'date_action': occupation.date_fin,
                    'date_formatee': timezone.localtime(occupation.date_fin).strftime(
                        '%d/%m/%Y a %H:%M'
                    ),
                    'utilisateur_nom': request.user.username,
                    'metadata': {},
                })

        serializer = HistoriqueItemSerializer(items, many=True)
        return Response(serializer.data)