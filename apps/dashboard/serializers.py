"""
apps/dashboard/serializers.py
=============================
Serres de validation/format des reponses du dashboard. Les objets
DashboardStats et ActivityItem sont construits en Python (services.py),
les serializers servent de contrat explicite pour la documentation
OpenAPI/Swagger et la securite de type.
"""

from rest_framework import serializers


class AlerteSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=[
        'eclosion_imminente', 'eclosion_retard', 'sevrage_imminent',
    ])
    titre = serializers.CharField()
    description = serializers.CharField()
    date = serializers.CharField()
    reference_id = serializers.CharField()


class ActiviteSerializer(serializers.Serializer):
    """Contrat conforme au type ActivityItem du frontend."""
    id = serializers.CharField()
    type = serializers.ChoiceField(choices=[
        'cage', 'pigeon', 'couple', 'reproduction', 'sortie',
    ])
    type_action = serializers.CharField()
    titre = serializers.CharField()
    description = serializers.CharField()
    date = serializers.CharField()
    badge = serializers.CharField()
    utilisateur = serializers.CharField(allow_null=True, required=False)
    metadata = serializers.DictField(required=False)


class DashboardStatsSerializer(serializers.Serializer):
    colombier = serializers.DictField()
    effectif = serializers.DictField()
    cages = serializers.DictField()
    couples = serializers.DictField() 
    reproduction = serializers.DictField()
    finances = serializers.DictField()
    naissances_par_mois = serializers.ListField(child=serializers.DictField())
    revenus_par_mois = serializers.ListField(child=serializers.DictField())
    alertes = AlerteSerializer(many=True)
