"""
apps/pigeons/views.py (v2)
==========================
Corrections :
1. SECURITY - scoping sur le proprietaire (avant : tous les pigeons de la
   base etaient visibles par tout utilisateur authentifie).
2. SOFT DELETE - le modele avait un `soft_delete()` jamais utilise : le
   destroy par defaut faisait un DELETE SQL irreversible. Le soft delete
   est applique et le queryset exclut les lignes supprimees.
3. FILTRES - statut / sexe / race / recherche / tri exploitent les
   filter_backends deja declares dans settings.py.
4. GENEALOGIE - le frontend appelait /pigeons/{id}/arbre/, /parents/,
   /freres-soeurs/ et /descendants/ : implémentes ici.
"""

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.ownership import OwnerOnlyPermission, OwnerQuerysetMixin

from .models import Pigeon
from .serializers import PigeonMiniSerializer, PigeonSerializer


def _mini(pigeon):
    """Représentation compacte d'un pigeon (types PigeonMini du front)."""
    return PigeonMiniSerializer(pigeon).data


class PigeonViewSet(OwnerQuerysetMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, OwnerOnlyPermission]
    serializer_class = PigeonSerializer
    queryset = Pigeon.objects.all()
    filterset_fields = ['statut', 'sexe', 'race']
    search_fields = ['matricule', 'race', 'couleur', 'notes']
    ordering_fields = ['created_at', 'date_naissance', 'matricule', 'statut']
    ordering = ['-created_at']

    def get_queryset(self):
        return (
            super().get_queryset()
            .filter(deleted_at__isnull=True)
            .select_related('pere', 'mere')
        )

    def perform_destroy(self, instance):
        # Soft delete au lieu du DELETE SQL par defaut.
        instance.soft_delete()

    # ------------------------------------------------------------------
    # GENEALOGIE
    # ------------------------------------------------------------------
    @action(detail=True, methods=['get'])
    def parents(self, request, pk=None):
        pigeon = self.get_object()
        return Response({
            'pere': _mini(pigeon.pere) if pigeon.pere else None,
            'mere': _mini(pigeon.mere) if pigeon.mere else None,
        })

    @action(detail=True, methods=['get'], url_path='freres-soeurs')
    def freres_soeurs(self, request, pk=None):
        pigeon = self.get_object()
        parents = [p for p in (pigeon.pere, pigeon.mere) if p]
        if not parents:
            return Response({'count': 0, 'results': []})

        from django.db.models import Q
        q = Q()
        if pigeon.pere:
            q |= Q(pere=pigeon.pere)
        if pigeon.mere:
            q |= Q(mere=pigeon.mere)

        fratrie = (
            Pigeon.objects.filter(q, deleted_at__isnull=True)
            .exclude(id=pigeon.id)
            .distinct()
        )
        return Response({
            'count': fratrie.count(),
            'results': PigeonMiniSerializer(fratrie, many=True).data,
        })

    @action(detail=True, methods=['get'])
    def arbre(self, request, pk=None):
        pigeon = self.get_object()
        profondeur = min(
            int(request.query_params.get('profondeur', 3) or 3), 5,
        )
        return Response({
            'pigeon': {
                'id': str(pigeon.id),
                'matricule': pigeon.matricule,
                'sexe': pigeon.sexe,
                'generation': 0,
            },
            'arbre': self._construire_arbre(pigeon, profondeur),
            'profondeur': profondeur,
        })

    def _construire_arbre(self, pigeon, profondeur):
        if pigeon is None or profondeur < 0:
            return None
        return {
            'id': str(pigeon.id),
            'matricule': pigeon.matricule,
            'sexe': pigeon.sexe,
            'generation': 0,
            'date_naissance': str(pigeon.date_naissance) if pigeon.date_naissance else None,
            'pere': self._construire_arbre(pigeon.pere, profondeur - 1),
            'mere': self._construire_arbre(pigeon.mere, profondeur - 1),
        }

    @action(detail=True, methods=['get'])
    def descendants(self, request, pk=None):
        pigeon = self.get_object()
        resultats = []
        self._collecter_descendants(pigeon, niveau=1, resultats=resultats)
        return Response({'count': len(resultats), 'results': resultats})

    def _collecter_descendants(self, pigeon, niveau, resultats, max_niveau=5):
        from django.db.models import Q
        if niveau > max_niveau:
            return
        enfants = (
            Pigeon.objects.filter(
                Q(pere=pigeon) | Q(mere=pigeon), deleted_at__isnull=True,
            ).distinct()
        )
        for enfant in enfants:
            relation = 'fils' if enfant.sexe == 'M' else 'fille'
            if niveau > 1:
                relation = 'petit-' + relation
            resultats.append({
                'niveau': niveau,
                'relation': relation,
                'pigeon': _mini(enfant),
            })
            self._collecter_descendants(enfant, niveau + 1, resultats)
