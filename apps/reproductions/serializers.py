"""
apps/reproductions/serializers.py (v2)
======================================
CONTRAT API - Le type Reproduction du frontend attend :
    couple_details { id, male: PigeonMini, femelle: PigeonMini },
    nombre_eclos, jeunes_details, statut ('incubation'|'eclosion'|'sevrage'|
    'termine'), statut_display, date_sevrage.
Le modele n'a ni `statut`, ni `nombre_eclos`, ni `date_sevrage` : ils sont
calcules ici (et une recommandation d'evolution du modele figure dans les
notes d'integration pour les rendre persistants).
"""

from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

from apps.couples.models import Couple
from apps.pigeons.serializers import PigeonMiniSerializer

from .models import Reproduction

DUREE_INCUBATION_JOURS = 18
DUREE_SEVRAGE_JOURS = 30

STATUT_LABELS = {
    'incubation': 'Incubation',
    'eclosion': 'Eclosion',
    'sevrage': 'Sevrage',
    'termine': 'Termine',
}


class CoupleMiniSerializer(serializers.ModelSerializer):
    male = PigeonMiniSerializer(read_only=True)
    femelle = PigeonMiniSerializer(read_only=True)

    class Meta:
        model = Couple
        fields = ['id', 'male', 'femelle']


class ReproductionSerializer(serializers.ModelSerializer):
    couple_details = CoupleMiniSerializer(source='couple', read_only=True)
    jeunes_details = PigeonMiniSerializer(source='jeunes', many=True, read_only=True)
    nombre_eclos = serializers.SerializerMethodField()
    statut = serializers.SerializerMethodField()
    statut_display = serializers.SerializerMethodField()
    date_sevrage = serializers.SerializerMethodField()

    class Meta:
        model = Reproduction
        fields = [
            'id', 'couple', 'couple_details',
            'date_ponte', 'date_eclosion', 'date_sevrage',
            'nombre_oeufs', 'nombre_eclos', 'nombre_jeunes',
            'jeunes', 'jeunes_details',
            'statut', 'statut_display', 'notes',
            'created_at', 'updated_at',
        ]

    def get_nombre_eclos(self, obj):
        if not obj.date_eclosion:
            return 0
        return min(obj.nombre_jeunes, obj.nombre_oeufs) if obj.nombre_jeunes else 0

    def get_statut(self, obj):
        today = timezone.localdate()
        if not obj.date_eclosion:
            return 'incubation'
        jours_depuis_eclosion = (today - obj.date_eclosion).days
        if jours_depuis_eclosion < DUREE_SEVRAGE_JOURS and obj.nombre_jeunes > 0:
            return 'sevrage'
        return 'termine'

    def get_statut_display(self, obj):
        return STATUT_LABELS[self.get_statut(obj)]

    def get_date_sevrage(self, obj):
        if obj.date_eclosion:
            return obj.date_eclosion + timedelta(days=DUREE_SEVRAGE_JOURS)
        return None

    def validate(self, attrs):
        date_ponte = attrs.get('date_ponte') or getattr(self.instance, 'date_ponte', None)
        date_eclosion = attrs.get('date_eclosion') or getattr(self.instance, 'date_eclosion', None)
        if date_ponte and date_eclosion and date_eclosion < date_ponte:
            raise serializers.ValidationError(
                "La date d'eclosion ne peut pas preceder la date de ponte."
            )
        if date_eclosion and date_ponte and (date_eclosion - date_ponte).days > 30:
            raise serializers.ValidationError(
                "L'eclosion est detectee plus de 30 jours apres la ponte : "
                'verifiez les dates saisies.'
            )
        return attrs
