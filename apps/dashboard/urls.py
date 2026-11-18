"""
apps/dashboard/urls.py
----------------------
A brancher dans backend/urls.py :
    path('api/', include('apps.dashboard.urls'))
"""

from django.urls import path

from .views import ActivitesView, DashboardStatsView

urlpatterns = [
    path('dashboard/stats/', DashboardStatsView.as_view(), name='dashboard-stats'),
    path('activites/', ActivitesView.as_view(), name='activites'),
]
