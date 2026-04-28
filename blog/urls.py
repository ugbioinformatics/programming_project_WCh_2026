from django.urls import path
from .views import BlogListView,BlogDetailView,BlogCreateView,suma,BlogDeleteView,smiles3de,smiles_page
from . import views


urlpatterns = [
   path("", BlogListView.as_view(), name="home"),
   path("post/smiles/", smiles_page, name="smiles_page"),
   path("post/<int:pk>/", BlogDetailView.as_view(), name="post_detail"),
   path("post/new/", BlogCreateView.as_view(), name="post_new"),
   path("post/suma/", suma, name="suma"),

   path("post/<int:pk>/delete/", BlogDeleteView.as_view(), name="post_delete"),

   path("smiles3d/", views.smiles3de, name="smiles3de"),

   path('xtb/', views.xtb_calc_view, name='xtb_calc'),
   path('download-g98/<int:post_id>/', views.download_g98, name='download_g98'),
]

