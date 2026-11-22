"""
apps/core/management/commands/backfill_owner.py
================================================
Assigne au premier superutilisateur toutes les lignes metier dont le
champ `owner` est NULL (donnees creees avant la v2 multi-tenant).

Lance automatiquement par render.yaml apres `migrate` :
    python manage.py backfill_owner

Idempotent : ne touche que les lignes owner__isnull=True, donc un
second lancement ne fait rien.
"""

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Attribue au premier superutilisateur les donnees sans proprietaire (owner NULL)."

    def handle(self, *args, **options):
        User = get_user_model()
        admin = (
            User.objects.filter(is_superuser=True)
            .order_by('id')
            .first()
        )
        if admin is None:
            self.stdout.write(self.style.WARNING(
                'Aucun superutilisateur trouve : backfill ignore.'
            ))
            return

        self.stdout.write(f'Backfill owner -> {admin.username} (id={admin.id})')
        total = 0
        for model in django_apps.get_models():
            champs = {f.name for f in model._meta.get_fields()}
            if 'owner' not in champs:
                continue
            try:
                count = model.objects.filter(owner__isnull=True).update(owner=admin)
            except Exception as exc:
                self.stdout.write(self.style.ERROR(f'{model.__name__} : {exc}'))
                continue
            if count:
                self.stdout.write(f'  {model.__name__} : {count} ligne(s) attribuee(s)')
                total += count

        if total:
            self.stdout.write(self.style.SUCCESS(
                f'Backfill termine : {total} ligne(s) attribuee(s) a {admin.username}.'
            ))
        else:
            self.stdout.write('Backfill termine : rien a faire (aucune ligne owner NULL).')