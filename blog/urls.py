from django.urls import path
from .views import (
    BlogListView,
    BlogDetailView,
    BlogUpdateView,
    BlogCreateView,
    BlogDeleteView,
    suma,
    smiles3de,
    smiles_page
)

urlpatterns = [

    path("", BlogListView.as_view(), name="home"),
    path("post/smiles/", smiles_page, name="smiles_page"),
    path("post/<int:pk>/", BlogDetailView.as_view(), name="post_detail"),
    path("post/new/", BlogCreateView.as_view(), name="post_new"),
    path("post/suma/", suma, name="suma"),
    path("post/<int:pk>/edit/", BlogUpdateView.as_view(), name="post_edit"),
    path("post/<int:pk>/delete/", BlogDeleteView.as_view(), name="post_delete"),

    path("api/smiles3d/", smiles3de, name='smiles3de'),
]
