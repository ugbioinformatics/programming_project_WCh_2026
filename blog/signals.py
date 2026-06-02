import os
import shutil
import logging

from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.conf import settings

from .models import Post

logger = logging.getLogger(__name__)


@receiver(post_delete, sender=Post)
def delete_on_post_del(sender, instance, **kwargs):
    dir_path = os.path.join(settings.MEDIA_ROOT, str(instance.id))
    try:
        if os.path.isdir(dir_path):
            shutil.rmtree(dir_path)
    except Exception as e:
        logger.error('Błąd podczas usuwania katalogu %s: %s', dir_path, e)
