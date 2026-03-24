from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import Post
import shutil
import os

@receiver(post_save, sender=Post)
def write_on_task_save(sender, instance, **kwargs):
      print("Zapis do bazy")
      print(instance.body)
def delete_on_post_del(sender, instance, **kwargs):
      if os.path.isdir(instance.plik_hash):
          shutil.rmtree(instance.plik_hash)