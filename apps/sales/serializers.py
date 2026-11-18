"""
apps/sales/serializers.py (v2)
==============================
Ajouts :
- details du pigeon (matricule, sexe, race) pour eviter un aller-retour
  supplementaire depuis le frontend.
- validation des champs conditionnels : une vente exige un prix et un
  acheteur ; un deces/perte exige au moins une cause ou des circonstances.
"""

from rest_framework import serializers

from apps.pigeons.serializers import PigeonMiniSerializer

from .models import Sortie


class SortieSerializer(serializers.ModelSerializer):
    pigeon_details = PigeonMiniSerializer(source='pigeon', read_only=True)
    type_sortie_display = serializers.CharField(
        source='get_type_sortie_display', read_only=True,
    )

    class Meta:
        model = Sortie
        fields = [
            'id', 'pigeon', 'pigeon_details', 'type_sortie',
            'type_sortie_display', 'date_sortie',
            'prix', 'acheteur', 'cause', 'circonstances',
            'notes', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']

    def validate(self, attrs):
        type_sortie = attrs.get('type_sortie') or getattr(
            self.instance, 'type_sortie', None,
        )
        prix = attrs.get('prix') or getattr(self.instance, 'prix', None)
        acheteur = attrs.get('acheteur') or getattr(self.instance, 'acheteur', None)
        cause = attrs.get('cause') or getattr(self.instance, 'cause', None)
        circonstances = attrs.get('circonstances') or getattr(
            self.instance, 'circonstances', None,
        )

        if type_sortie == 'vente' and not prix:
            raise serializers.ValidationError(
                {'prix': 'Le prix est obligatoire pour une vente.'}
            )
        if type_sortie in ('deces', 'perte') and not (cause or circonstances):
            raise serializers.ValidationError(
                {'cause': 'Renseignez la cause ou les circonstances.'}
            )
        if type_sortie == 'vente' and acheteur and len(acheteur) < 2:
            raise serializers.ValidationError({'acheteur': 'Nom trop court.'})
        return attrs
