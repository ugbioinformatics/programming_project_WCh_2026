from django.urls import path
from . import views

app_name = 'xtb'

urlpatterns = [
    path('',              views.index,  name='index'),
    path('<int:pk>/',     views.detail, name='detail'),
    path('<int:pk>/del/', views.delete, name='delete'),
]
