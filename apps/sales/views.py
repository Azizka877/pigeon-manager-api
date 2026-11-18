"""
apps/sales/views.py (v2)
========================
Corrections :
1. SECURITY - scoping proprietaire.
2. Le statut du pigeon n'est plus modifie dans Sortie.save() (effet de bord
   silencieux qui se declenchait aussi a chaque PUT/edition) : la logique
   est centralisee dans services.traiter_sortie, appelee ici en
   perform_create, dans une transaction.
3. DELETE revert le statut du pigeon (annulation) au lieu de laisser une
   sortie "fantome" dont l'effet persiste.
"""

from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from apps.core.ownership import OwnerOnlyPermission, OwnerQuerysetMixin

from .models import Sortie
from .serializers import SortieSerializer
from .services import annuler_sortie, traiter_sortie


class SortieViewSet(OwnerQuerysetMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, OwnerOnlyPermission]
    serializer_class = SortieSerializer
    filterset_fields = ['type_sortie', 'date_sortie', 'pigeon']

    def get_queryset(self):
        return (
            super().get_queryset()
            .select_related('pigeon')
        )

    def perform_create(self, serializer):
        sortie = serializer.save()
        # Effets metier atomiques : statut du pigeon + liberation cage +
        # rupture eventuelle du couple.
        traiter_sortie(sortie)

    def perform_destroy(self, instance):
        annuler_sortie(instance)
        instance.delete()
