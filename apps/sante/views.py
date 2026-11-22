from datetime import timedelta

from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import Soin, Rappel
from .serializers import SoinSerializer, RappelSerializer, PigeonCompactSerializer


class SoinViewSet(viewsets.ModelViewSet):
    """CRUD des soins : /api/sante/soins/"""
    serializer_class = SoinSerializer
    filterset_fields = ['pigeon', 'type_soin']
    search_fields = ['produit', 'notes']
    ordering_fields = ['date_soin', 'created_at']

    def get_queryset(self):
        return Soin.objects.select_related('pigeon').all()


class RappelViewSet(viewsets.ModelViewSet):
    """CRUD des rappels : /api/sante/rappels/"""
    serializer_class = RappelSerializer
    filterset_fields = ['pigeon', 'type_rappel', 'fait']
    search_fields = ['titre', 'notes']
    ordering_fields = ['date_rappel', 'created_at']

    def get_queryset(self):
        return Rappel.objects.select_related('pigeon').all()


def _pigeon_dict(pigeon):
    if pigeon is None:
        return None
    return PigeonCompactSerializer(pigeon).data


@api_view(['GET'])
def agenda(request):
    """Événements du calendrier sur une période :
    ?debut=2026-11-01&fin=2026-11-30 (défaut : aujourd'hui -> +90 jours)

    Retourne 3 sources d'événements :
    - 'rappel'      : rappels manuels
    - 'soin'        : soins réalisés (interventions)
    - 'rappel_soin' : rappels automatiques générés par les soins
    """
    aujourdhui = timezone.localdate()
    try:
        debut = timezone.datetime.fromisoformat(
            request.query_params.get('debut') or (aujourdhui - timedelta(days=7)).isoformat()
        ).date()
        fin = timezone.datetime.fromisoformat(
            request.query_params.get('fin') or (aujourdhui + timedelta(days=90)).isoformat()
        ).date()
    except ValueError:
        return Response({'detail': 'Format de date invalide (attendu : YYYY-MM-DD)'}, status=400)

    evenements = []

    # 1) Rappels manuels
    for r in Rappel.objects.filter(date_rappel__range=[debut, fin]).select_related('pigeon'):
        evenements.append({
            'id': f'rappel-{r.id}',
            'db_id': r.id,
            'source': 'rappel',
            'titre': r.titre,
            'type': r.type_rappel,
            'date': r.date_rappel.isoformat(),
            'fait': r.fait,
            'pigeon': _pigeon_dict(r.pigeon),
            'notes': r.notes,
        })

    # 2) Soins réalisés
    for s in Soin.objects.filter(date_soin__range=[debut, fin]).select_related('pigeon'):
        evenements.append({
            'id': f'soin-{s.id}',
            'db_id': s.id,
            'source': 'soin',
            'titre': f"{s.produit}",
            'type': s.type_soin,
            'date': s.date_soin.isoformat(),
            'fait': None,
            'pigeon': _pigeon_dict(s.pigeon),
            'notes': s.dose,
        })

    # 3) Rappels automatiques générés par les soins
    for s in Soin.objects.filter(rappel_jours__gt=0).select_related('pigeon'):
        date_rappel = s.date_rappel
        if date_rappel and debut <= date_rappel <= fin:
            evenements.append({
                'id': f'rappel-soin-{s.id}',
                'db_id': s.id,
                'source': 'rappel_soin',
                'titre': f"Rappel : {s.produit}",
                'type': 'soin',
                'date': date_rappel.isoformat(),
                'fait': None,
                'pigeon': _pigeon_dict(s.pigeon),
                'notes': f"Rappel automatique du soin du {s.date_soin.isoformat()}",
            })

    evenements.sort(key=lambda e: e['date'])
    return Response({'debut': debut.isoformat(), 'fin': fin.isoformat(), 'evenements': evenements})


@api_view(['GET'])
def stats(request):
    """Chiffres clés santé pour le dashboard et les badges de navigation."""
    aujourdhui = timezone.localdate()
    limite_7j = aujourdhui + timedelta(days=7)
    il_y_a_30j = aujourdhui - timedelta(days=30)

    prochains = (
        Rappel.objects.filter(fait=False, date_rappel__lte=limite_7j)
        .select_related('pigeon')
        .order_by('date_rappel')[:6]
    )

    return Response({
        'rappels_en_retard': Rappel.objects.filter(fait=False, date_rappel__lt=aujourdhui).count(),
        'rappels_7_jours': Rappel.objects.filter(fait=False, date_rappel__range=[aujourdhui, limite_7j]).count(),
        'soins_30_jours': Soin.objects.filter(date_soin__gte=il_y_a_30j).count(),
        'aujourdhui': aujourdhui.isoformat(),
        'prochains': RappelSerializer(prochains, many=True).data,
    })