from django.contrib.auth.models import User
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .serializers import ChangePasswordSerializer, UserSerializer


class UserViewSet(viewsets.ModelViewSet):
    """
    Self-service du compte : un colombophile ne voit et ne modifie QUE son
    propre compte. Les staffs (is_staff) conservent un accès complet au
    registre pour le support — la promotion is_staff elle-même reste
    réservée à l'admin Django (lecture seule dans le sérialiseur).
    """

    queryset = User.objects.all()
    serializer_class = UserSerializer

    # ── Verrou de sécurité n°1 : le queryset ne renvoie que soi-même ──
    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.user.is_staff:
            return qs
        return qs.filter(pk=self.request.user.pk)

    # ── Verrou n°2 (défense en profondeur) : un objet étranger → 403 ──
    def get_object(self):
        obj = super().get_object()
        if obj != self.request.user and not self.request.user.is_staff:
            self.permission_denied(self.request, message='Non autorisé')
        return obj

    # ── GET /api/users/me/ : profil de l'utilisateur connecté ──
    @action(detail=False, methods=['get'], url_path='me')
    def me(self, request):
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)

    # ── POST /api/users/{id}/change_password/ : soi-même uniquement ──
    @action(detail=True, methods=['post'], url_path='change_password')
    def change_password(self, request, pk=None):
        user = self.get_object()  # verrouillé : le propriétaire (ou un staff)
        serializer = ChangePasswordSerializer(data=request.data, context={'target': user})
        serializer.is_valid(raise_exception=True)

        user.set_password(serializer.validated_data['new_password'])
        user.save()
        return Response({'detail': 'Mot de passe changé avec succès'})

    # ── DELETE : filet de sécurité (déjà couvert par les verrous) ──
    def destroy(self, request, *args, **kwargs):
        user = self.get_object()
        if user != request.user and not request.user.is_staff:
            return Response({'detail': 'Non autorisé'}, status=status.HTTP_403_FORBIDDEN)
        return super().destroy(request, *args, **kwargs)