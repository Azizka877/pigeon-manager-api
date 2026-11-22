from rest_framework import serializers

from apps.pigeons.models import Pigeon

from .models import Soin, Rappel


class PigeonCompactSerializer(serializers.ModelSerializer):
    """Infos minimales du pigeon pour afficher la fiche côté frontend."""

    class Meta:
        model = Pigeon
        fields = ['id', 'matricule', 'race', 'sexe']


class SoinSerializer(serializers.ModelSerializer):
    pigeon = serializers.PrimaryKeyRelatedField(queryset=Pigeon.objects.all())
    pigeon_detail = PigeonCompactSerializer(source='pigeon', read_only=True)
    date_rappel = serializers.ReadOnlyField()

    class Meta:
        model = Soin
        fields = [
            'id', 'pigeon', 'pigeon_detail', 'type_soin', 'produit',
            'dose', 'date_soin', 'rappel_jours', 'date_rappel',
            'notes', 'created_at', 'updated_at',
        ]


class RappelSerializer(serializers.ModelSerializer):
    pigeon = serializers.PrimaryKeyRelatedField(
        queryset=Pigeon.objects.all(),
        required=False,
        allow_null=True,
    )
    pigeon_detail = PigeonCompactSerializer(source='pigeon', read_only=True)

    class Meta:
        model = Rappel
        fields = [
            'id', 'titre', 'type_rappel', 'date_rappel', 'fait',
            'pigeon', 'pigeon_detail', 'notes', 'created_at', 'updated_at',
        ]