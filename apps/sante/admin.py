from django.contrib import admin

from .models import Soin, Rappel


@admin.register(Soin)
class SoinAdmin(admin.ModelAdmin):
    list_display = ['produit', 'type_soin', 'pigeon', 'date_soin', 'rappel_jours']
    list_filter = ['type_soin', 'date_soin']
    search_fields = ['produit', 'notes']
    date_hierarchy = 'date_soin'


@admin.register(Rappel)
class RappelAdmin(admin.ModelAdmin):
    list_display = ['titre', 'type_rappel', 'date_rappel', 'fait', 'pigeon']
    list_filter = ['type_rappel', 'fait']
    search_fields = ['titre', 'notes']
    list_editable = ['fait']