"""
apps/dashboard/views.py
=======================
Deux endpoints REST :
    GET /api/dashboard/stats/   -> DashboardStats (KPIs, series, alertes)
    GET /api/activites/         -> { count, results: ActivityItem[] }
                                   parametres : ?limit=10&days=30
Le frontend appelait deja /activites/ (useRecentActivity) sans qu'il
existe cote serveur ; il est implemente ici.
"""

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import ActiviteSerializer, DashboardStatsSerializer
from .services import build_dashboard_stats, build_recent_activities


class DashboardStatsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        stats = build_dashboard_stats(request.user)
        serializer = DashboardStatsSerializer(stats)
        return Response(serializer.data)


class ActivitesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            limit = min(max(int(request.query_params.get('limit', 10)), 1), 100)
        except (TypeError, ValueError):
            limit = 10
        try:
            days = min(max(int(request.query_params.get('days', 30)), 1), 365)
        except (TypeError, ValueError):
            days = 30

        activites = build_recent_activities(request.user, limit=limit, days=days)
        serializer = ActiviteSerializer(activites['results'], many=True)
        return Response({'count': activites['count'], 'results': serializer.data})
