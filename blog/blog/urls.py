from django.urls import path
from .views import BlogListView, BlogDetailView, BlogCreateView, BlogUpdateView, BlogDeleteView, edit_blog, suma

urlpatterns = [
    path("post/new/", BlogCreateView.as_view(), name="post_new"),
    path("post/suma/", suma, name="suma"), 
    path("post/<int:pk>/", BlogDetailView.as_view(), name="post_detail"),
    #path("post/<int:pk>/edit/", BlogUpdateView.as_view(), name="post_edit"),
    path("post/<int:pk>/edit/", edit_blog, name="post_edit"),
    path("", BlogListView.as_view(), name="home"),
    path("post/<int:pk>/delete/", BlogDeleteView.as_view(),
        name="post_delete"), 
]

from django.conf import settings
from django.conf.urls.static import static
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL,
                          document_root=settings.MEDIA_ROOT)