from rest_framework import serializers

from apps.couples.serializers import CoupleSerializer
from apps.pigeons.serializers import PigeonSerializer

from .models import Cage, Occupation


class CageSerializer(serializers.ModelSerializer):
    statut_actuel = serializers.SerializerMethodField()
    occupation_actuelle = serializers.SerializerMethodField()

    class Meta:
        model = Cage
        fields = [
            'id', 'numero', 'nom', 'superficie',
            'position_x', 'position_y', 'est_active',
            'statut_actuel', 'occupation_actuelle',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_statut_actuel(self, obj):
        return obj.statut_actuel

    def get_occupation_actuelle(self, obj):
        # Exploite le prefetch 'occupations' du ViewSet : aucune requete
        # supplementaire n'est emise ici.
        occupation = obj.occupation_actuelle
        if not occupation:
            return None
        return {
            'type': occupation.type_occupation,
            'date_debut': occupation.date_debut,
            'pigeon': (
                PigeonSerializer(occupation.pigeon).data
                if occupation.pigeon else None
            ),
            'couple': (
                CoupleSerializer(occupation.couple).data
                if occupation.couple else None
            ),
        }


class OccupationSerializer(serializers.ModelSerializer):
    cage_numero = serializers.CharField(source='cage.numero', read_only=True)
    pigeon_details = PigeonSerializer(source='pigeon', read_only=True)
    couple_details = CoupleSerializer(source='couple', read_only=True)

    class Meta:
        model = Occupation
        fields = [
            'id', 'cage', 'cage_numero', 'pigeon', 'pigeon_details',
            'couple', 'couple_details', 'type_occupation',
            'date_debut', 'date_fin',
        ]
        read_only_fields = ['id', 'date_debut']


class HistoriqueItemSerializer(serializers.Serializer):
    """
    Journal d'une cage - conforme au type HistoriqueItem du frontend :
    { id, type_action, description, date_action, date_formatee,
      utilisateur_nom, metadata }
    """
    id = serializers.CharField()
    type_action = serializers.ChoiceField(choices=[
        'occupation', 'liberation', 'nettoyage', 'creation', 'modification',
    ])
    description = serializers.CharField()
    date_action = serializers.DateTimeField()
    date_formatee = serializers.CharField()
    utilisateur_nom = serializers.CharField(allow_blank=True)
    metadata = serializers.DictField(required=False)