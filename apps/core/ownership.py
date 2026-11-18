"""
apps/core/ownership.py
======================
Isolation multi-locataire (multi-tenant) centralisee.

Probleme corrige :
    Les ViewSets (Cage, Pigeon, Couple, Reproduction, Sortie) exposaient
    `queryset = Model.objects.all()` : tout utilisateur authentifie voyait et
    modifiait les donnees de TOUS les autres eleveurs. Seul ColombierConfig
    etait correctement isole.

Solution :
    1. `OwnedModel`  - modele abstrait qui ajoute un FK `owner` vers l'utilisateur.
       Faire heriter Pigeon, Cage, Couple, Reproduction, Sortie de ce modele,
       puis executer :
           python manage.py makemigrations pigeons cages couples reproductions sales
           python manage.py migrate
    2. `OwnerQuerysetMixin` - mixin DRF qui :
           - filtre automatiquement le queryset sur l'utilisateur connecte
           - attribue owner=request.user a la creation
           - interdit l'acces aux objets d'un autre proprietaire (404, pas 403,
             pour ne pas reveler l'existence des objets).
"""

from django.conf import settings
from django.db import models
from rest_framework.permissions import IsAuthenticated


class OwnedModel(models.Model):
    """
    Modele abstrait : ajoute le champ `owner` a tous les modeles metier.
    null=True le temps de la migration initiale (backfill des donnees
    existantes), a passer en null=False apres le backfill si souhaite.
    """
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='%(class)s_set',
        null=True,
        blank=True,
        verbose_name='Propriétaire',
    )

    class Meta:
        abstract = True


class OwnerQuerysetMixin:
    """
    Mixin DRF : scoping systematique sur l'utilisateur connecte.

    Utilisation :
        class CageViewSet(OwnerQuerysetMixin, viewsets.ModelViewSet):
            queryset = Cage.objects.all()          # queryset de REFERENCE
            serializer_class = CageSerializer

    Le `queryset` de classe reste utile pour le routeur / le schema OpenAPI,
    mais get_queryset() le re-filtre TOUJOURS sur request.user.
    """
    owner_field = 'owner'

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if not user.is_authenticated:
            return qs.none()
        return qs.filter(**{self.owner_field: user})

    def perform_create(self, serializer):
        serializer.save(**{self.owner_field: self.request.user})


class OwnerOnlyPermission(IsAuthenticated):
    """
    Garde-fou supplementaire : verifie que l'objet touche appartient
    a l'utilisateur (defensif, utile si une action custom contourne
    get_queryset).
    """
    def has_object_permission(self, request, view, obj):
        if not super().has_permission(request, view):
            return False
        owner = getattr(obj, getattr(view, 'owner_field', 'owner'), None)
        return owner is None or owner == request.user
