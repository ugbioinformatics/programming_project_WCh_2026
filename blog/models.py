from django.db import models
from django.urls import reverse

def user_directory_path(instance, filename):
     # file will be uploaded to MEDIA_ROOT/<id>/plik.pdb
      return '{0}/{1}'.format(instance.id, 'plik.txt')

class Post(models.Model):
    title = models.CharField(max_length=200)
#    author = models.ForeignKey(
#        "auth.User",
#        on_delete=models.CASCADE,
#    )
    author = models.CharField(max_length=20,default='')
    body = models.TextField()

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("post_detail", kwargs={"pk": self.pk})
        
