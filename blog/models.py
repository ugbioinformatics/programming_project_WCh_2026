from django.db import models
from django.urls import reverse

def user_directory_path(instance, filename):
     # file will be uploaded to MEDIA_ROOT/<id>/plik.pdb
      return '{0}/{1}'.format(instance.id, 'start.xyz')

class Post(models.Model):
    title = models.CharField(max_length=200)
#    author = models.ForeignKey(
#        "auth.User",
#        on_delete=models.CASCADE,
#    )
    author = models.CharField(max_length=20,default='')
    smiles = models.TextField(default='')
    plik1 = models.FileField(default='',upload_to=user_directory_path)
  
    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("post_detail", kwargs={"pk": self.pk})

class XTBCalculation(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    input_type = models.CharField(max_length=10, choices=[('xyz', 'XYZ file'), ('smiles', 'SMILES')])
    smiles = models.TextField(blank=True)
    input_xyz = models.TextField(blank=True)       # zawartość pliku start.xyz
    output_log = models.TextField(blank=True)      # stdout z xtb
    optimized_xyz = models.TextField(blank=True)   # xtbopt.xyz po obliczeniach
    energy = models.FloatField(null=True, blank=True)  # energia wyciągnięta z logu
    status = models.CharField(max_length=20, default='pending')  # pending/done/error

    def __str__(self):
        return f"XTB #{self.pk} ({self.status}) {self.created_at:%Y-%m-%d %H:%M}"
