from rest_framework import serializers

from .models import Pigeon


def calculer_age(date_naissance):
    """Age en annees revolues, ou None si pas de date."""
    if not date_naissance:
        return None
    from datetime import date
    today = date.today()
    return today.year - date_naissance.year - (
        (today.month, today.day) < (date_naissance.month, date_naissance.day)
    )


class PigeonMiniSerializer(serializers.ModelSerializer):
    sexe_display = serializers.CharField(source='get_sexe_display', read_only=True)
    generation = serializers.SerializerMethodField()

    class Meta:
        model = Pigeon
        fields = ['id', 'matricule', 'sexe', 'sexe_display', 'race', 'couleur', 'generation']

    def get_generation(self, obj):
        return calculer_age(obj.date_naissance) or 0


class PigeonSerializer(serializers.ModelSerializer):
    age = serializers.SerializerMethodField()
    sexe_display = serializers.CharField(source='get_sexe_display', read_only=True)
    statut_display = serializers.CharField(source='get_statut_display', read_only=True)
    pere_matricule = serializers.CharField(source='pere.matricule', read_only=True, default=None)
    mere_matricule = serializers.CharField(source='mere.matricule', read_only=True, default=None)

    class Meta:
        model = Pigeon
        fields = [
            'id', 'matricule', 'sexe', 'sexe_display', 'race',
            'date_naissance', 'age', 'couleur', 'poids',
            'pere', 'pere_matricule', 'mere', 'mere_matricule',
            'statut', 'statut_display',
            'notes', 'created_at', 'updated_at',
        ]

    def get_age(self, obj):
        return calculer_age(obj.date_naissance)

    def validate_matricule(self, value):
        qs = Pigeon.objects.filter(matricule=value, deleted_at__isnull=True)
        if self.instance:
            qs = qs.exclude(id=self.instance.id)
        user = self.context['request'].user
        if qs.filter(owner=user).exists():
            raise serializers.ValidationError(
                f'Le matricule {value} existe deja dans votre colombier.'
            )
        return value