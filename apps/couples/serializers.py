from rest_framework import serializers

from apps.pigeons.serializers import PigeonSerializer

from .models import Couple


class CoupleSerializer(serializers.ModelSerializer):
    male_details = PigeonSerializer(source='male', read_only=True)
    femelle_details = PigeonSerializer(source='femelle', read_only=True)
    reproductions_count = serializers.SerializerMethodField()

    class Meta:
        model = Couple
        fields = [
            'id', 'male', 'male_details', 'femelle', 'femelle_details',
            'date_formation', 'date_rupture', 'statut', 'notes',
            'reproductions_count',
        ]
        read_only_fields = ['id', 'date_rupture', 'statut']

    def get_reproductions_count(self, obj):
        return obj.reproductions.count()

    def validate(self, attrs):
        male = attrs.get('male') or getattr(self.instance, 'male', None)
        femelle = attrs.get('femelle') or getattr(self.instance, 'femelle', None)

        if male is None or femelle is None:
            raise serializers.ValidationError(
                'Un couple requiert un male et une femelle.'
            )
        if male.id == femelle.id:
            raise serializers.ValidationError(
                'Un pigeon ne peut pas former un couple avec lui-meme.'
            )
        if male.sexe != 'M':
            raise serializers.ValidationError(
                f'{male.matricule} n\'est pas un male.'
            )
        if femelle.sexe != 'F':
            raise serializers.ValidationError(
                f'{femelle.matricule} n\'est pas une femelle.'
            )

        # Un pigeon ne peut etre dans qu'un seul couple actif.
        qs = Couple.objects.filter(statut='actif')
        if self.instance is not None:
            qs = qs.exclude(id=self.instance.id)
        if qs.filter(male=male).exists():
            raise serializers.ValidationError(
                f'{male.matricule} appartient deja a un couple actif.'
            )
        if qs.filter(femelle=femelle).exists():
            raise serializers.ValidationError(
                f'{femelle.matricule} appartient deja a un couple actif.'
            )
        return attrs