from django.db import models
from django.utils import timezone


class Calculation(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Oczekuje'),
        ('running', 'W trakcie'),
        ('done', 'Zakończone'),
        ('error', 'Błąd'),
    ]
    INPUT_CHOICES = [
        ('xyz',    'Plik XYZ'),
        ('smiles', 'SMILES'),
    ]
    METHOD_CHOICES = [
        ('gfn2',  'GFN2-xTB'),
        ('gfn1',  'GFN1-xTB'),
        ('gfnff', 'GFN-FF'),
        ('gfn0',  'GFN0-xTB'),
    ]

    name         = models.CharField(max_length=200, verbose_name='Nazwa')
    input_type   = models.CharField(max_length=10, choices=INPUT_CHOICES, default='xyz')
    smiles       = models.CharField(max_length=500, blank=True, verbose_name='SMILES')
    xyz_file     = models.FileField(upload_to='xtb_uploads/', blank=True, null=True, verbose_name='Plik XYZ')
    method       = models.CharField(max_length=10, choices=METHOD_CHOICES, default='gfn2')
    optimize     = models.BooleanField(default=True, verbose_name='Optymalizacja geometrii')
    charge       = models.IntegerField(default=0, verbose_name='Ładunek')
    multiplicity = models.IntegerField(default=1, verbose_name='Multipletowość')

    status       = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    output_log   = models.TextField(blank=True, verbose_name='Log xTB')
    energy       = models.FloatField(null=True, blank=True, verbose_name='Energia (Eh)')
    result_dir   = models.CharField(max_length=500, blank=True)

    created_at   = models.DateTimeField(default=timezone.now)
    finished_at  = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Obliczenie xTB'
        verbose_name_plural = 'Obliczenia xTB'

    def __str__(self):
        return f"{self.name} ({self.get_method_display()}) – {self.get_status_display()}"

    def energy_kcal(self):
        if self.energy is not None:
            return round(self.energy * 627.509, 4)
        return None
