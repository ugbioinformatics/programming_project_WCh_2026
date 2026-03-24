
# Create your models here.
from django.db import models
from django.urls import reverse

def user_directory_path(instance, filename):
     # file will be uploaded to MEDIA_ROOT//plik.pdb
      return '{0}/{1}'.format(instance.plik_hash, 'plik.dane')

class Post(models.Model):
    title = models.CharField(max_length=200)
    #author = models.ForeignKey(
    #    "auth.User",
    #    on_delete=models.CASCADE,
    #)
    author = models.CharField(max_length=20)
    body = models.TextField()
    suma = models.FloatField(blank=True, null=True)

    guzik = models.BooleanField(default = False)

    odch = models.FloatField(blank=True, null=True)
    śr = models.FloatField(blank=True, null=True)
    var = models.FloatField(blank=True, null=True)
    
    #state = models.BooleanField(default=False)
    #email = models.EmailField(blank=True, null=True)
    
    plik1 = models.FileField(default='',upload_to=user_directory_path)
    plik_hash = models.CharField(blank=True, null=True, max_length=256)
    
    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("post_detail", kwargs={"pk": self.pk})
