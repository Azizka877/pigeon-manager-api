from django.db import transaction
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.ownership import OwnerOnlyPermission, OwnerQuerysetMixin

from .models import Couple
from .serializers import CoupleSerializer


class CoupleViewSet(OwnerQuerysetMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, OwnerOnlyPermission]
    serializer_class = CoupleSerializer

    def get_queryset(self):
        qs = (
            super().get_queryset()
            .select_related('male', 'femelle')
        )
        # Par defaut on n'affiche que les couples actifs ; ?statut=rompu ou
        # ?statut=tous pour elargir (utile pour l'historique d'elevage).
        statut = self.request.query_params.get('statut', 'actif')
        if statut in ('actif', 'rompu'):
            return qs.filter(statut=statut)
        return qs

    @action(detail=True, methods=['post'])
    @transaction.atomic
    def rompre(self, request, pk=None):
        couple = self.get_object()
        if couple.statut != 'actif':
            return Response(
                {'detail': 'Ce couple est deja rompu.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        date_rupture = request.data.get('date_rupture')
        couple.rompre(date_rupture)

        # Liberation de la cage occupee par ce couple (anciennement
        # faite cote client, fragile et sujete aux race conditions).
        from apps.cages.models import Occupation
        Occupation.objects.filter(
            couple=couple, date_fin__isnull=True,
        ).update(date_fin=timezone.now())

        serializer = self.get_serializer(couple)
        return Response(serializer.data)