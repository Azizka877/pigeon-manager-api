from django.contrib.auth.models import User
from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'is_staff', 'is_active', 'date_joined', 'last_login',
        ]
        read_only_fields = [
            'id', 'username', 'is_staff', 'is_active', 'date_joined', 'last_login',
        ]


class ChangePasswordSerializer(serializers.Serializer):
    """Ancien + nouveau mot de passe, validés contre le compte ciblé."""

    old_password = serializers.CharField(write_only=True, trim_whitespace=False)
    new_password = serializers.CharField(
        write_only=True, trim_whitespace=False, min_length=8,
    )

    def validate_old_password(self, value):
        target = self.context.get('target')
        if target is not None and not target.check_password(value):
            raise serializers.ValidationError('Mot de passe actuel incorrect')
        return value

    def validate_new_password(self, value):
        target = self.context.get('target')
        # Applique AUTH_PASSWORD_VALIDATORS (longueur, mots de passe courants,
        # purement numériques, similarité avec les attributs du compte).
        validate_password(value, user=target)
        return value