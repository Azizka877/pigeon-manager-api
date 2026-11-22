from datetime import timedelta

from django.db import models


class Soin(models.Model):
    """Intervention de santé réalisée sur un pigeon
    (vaccin, traitement, vermifuge, contrôle vétérinaire...)."""

    TYPES_SOIN = [
        ('vaccin', 'Vaccin'),
        ('traitement', 'Traitement'),
        ('vermifuge', 'Vermifuge'),
        ('vitamines', 'Vitamines / Compléments'),
        ('controle', 'Contrôle vétérinaire'),
        ('autre', 'Autre'),
    ]

    pigeon = models.ForeignKey(
        'pigeons.Pigeon',
        on_delete=models.CASCADE,
        related_name='soins',
        verbose_name='Pigeon concerné'
    )
    type_soin = models.CharField(
        max_length=20,
        choices=TYPES_SOIN,
        default='traitement',
        verbose_name='Type de soin'
    )
    produit = models.CharField(
        max_length=200,
        verbose_name='Produit / Vaccin'
    )
    dose = models.CharField(
        max_length=100,
        blank=True,
        verbose_name='Dose / Posologie'
    )
    date_soin = models.DateField(
        verbose_name='Date du soin'
    )
    rappel_jours = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name='Rappel (jours après)',
        help_text='Laisser vide ou 0 = pas de rappel automatique'
    )
    notes = models.TextField(
        blank=True,
        verbose_name='Notes'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'sante_soin'
        ordering = ['-date_soin', '-created_at']
        verbose_name = 'Soin'
        verbose_name_plural = 'Soins'

    def __str__(self):
        return f"{self.produit} ({self.get_type_soin_display()})"

    @property
    def date_rappel(self):
        """Date du rappel automatique = date du soin + N jours."""
        if self.rappel_jours:
            return self.date_soin + timedelta(days=self.rappel_jours)
        return None


class Rappel(models.Model):
    """Rappel manuel du colombier (rendez-vous veto, mirage,
    nettoyage, éclosion à surveiller...)."""

    TYPES_RAPPEL = [
        ('soin', 'Soin / Vétérinaire'),
        ('reproduction', 'Reproduction'),
        ('entretien', 'Entretien / Nettoyage'),
        ('autre', 'Autre'),
    ]

    titre = models.CharField(
        max_length=200,
        verbose_name='Titre du rappel'
    )
    type_rappel = models.CharField(
        max_length=20,
        choices=TYPES_RAPPEL,
        default='soin',
        verbose_name='Type de rappel'
    )
    date_rappel = models.DateField(
        verbose_name='Date du rappel'
    )
    fait = models.BooleanField(
        default=False,
        verbose_name='Fait'
    )
    pigeon = models.ForeignKey(
        'pigeons.Pigeon',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='rappels',
        verbose_name='Pigeon concerné'
    )
    notes = models.TextField(
        blank=True,
        verbose_name='Notes'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'sante_rappel'
        ordering = ['date_rappel']
        verbose_name = 'Rappel'
        verbose_name_plural = 'Rappels'

    def __str__(self):
        return f"{self.titre} — {self.date_rappel}"