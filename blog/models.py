from django.db import models
from django.urls import reverse
from django.contrib.auth.models import User


def user_directory_path(instance, filename):
    # plik zostanie zapisany do MEDIA_ROOT/<id>/start.xyz
    return '{0}/{1}'.format(instance.id, 'start.xyz')


class Post(models.Model):
    title = models.CharField(max_length=200)
    author = models.ForeignKey(User, on_delete=models.CASCADE, blank=True, null=True)
    smiles = models.TextField(default='')
    plik1 = models.FileField(default='', upload_to=user_directory_path)
    created_at = models.DateTimeField(auto_now_add=True)
    input_type = models.CharField(
        max_length=10,
        choices=[('xyz', 'XYZ file'), ('smiles', 'SMILES')],
        default='SMILES',
    )
    input_xyz = models.TextField(blank=True, default='')       # zawartość pliku start.xyz
    output_log = models.TextField(blank=True, default='')      # stdout z xtb
    optimized_xyz = models.TextField(blank=True, default='')   # xtbopt.xyz po obliczeniach
    energy = models.FloatField(null=True, blank=True, default=0)  # energia wyciągnięta z logu
    status = models.CharField(max_length=20, default='pending')   # pending / done / error
    frequencies = models.JSONField(blank=True, null=True)
    hessian_log = models.TextField(blank=True, null=True)
    has_imaginary = models.BooleanField(default=False)

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('post_detail', kwargs={'pk': self.pk})


class XTBCalculation(models.Model):
    """
    Alternatywny model dla widoku /xtb/ (xtb_calc_view).
    Przechowuje pojedynczą kalkulację bez powiązania z użytkownikiem.
    """
    created_at = models.DateTimeField(auto_now_add=True)
    input_type = models.CharField(max_length=10, choices=[('xyz', 'XYZ file'), ('smiles', 'SMILES')])
    smiles = models.TextField(blank=True)
    input_xyz = models.TextField(blank=True)
    output_log = models.TextField(blank=True)
    optimized_xyz = models.TextField(blank=True)
    energy = models.FloatField(null=True, blank=True)
    status = models.CharField(max_length=20, default='pending')  # pending / done / error

    def __str__(self):
        return f'XTB #{self.pk} ({self.status}) {self.created_at:%Y-%m-%d %H:%M}'
