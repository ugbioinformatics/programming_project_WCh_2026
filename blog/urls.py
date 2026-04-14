from django.urls import path
from .views import BlogListView,BlogDetailView,BlogCreateView,suma,BlogDeleteView
from . import views


urlpatterns = [
   path("post/<int:pk>/", BlogDetailView.as_view(), name="post_detail"),
   path("", BlogListView.as_view(), name="home"),
   path("post/new/", BlogCreateView.as_view(), name="post_new"), # new  
   path("post/suma/", suma, name="suma"), 

   path("post/<int:pk>/delete/", BlogDeleteView.as_view(),name="post_delete"),
   path('xtb/', views.xtb_calc_view, name='xtb_calc'),
 
]

