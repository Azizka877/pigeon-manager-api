from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import SoinViewSet, RappelViewSet, agenda, stats

router = DefaultRouter()
router.register('soins', SoinViewSet, basename='soin')
router.register('rappels', RappelViewSet, basename='rappel')

urlpatterns = [
    path('', include(router.urls)),
    path('agenda/', agenda, name='sante-agenda'),
    path('stats/', stats, name='sante-stats'),
]