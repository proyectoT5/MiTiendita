from . import views
from django.urls import path


urlpatterns = [
    path('',views.dashboard_view, name='dashboard'),
    path('productos/', views.productos_view, name='productos_lista'),
    path('productos/agregar/', views.productos_agregar_view, name='productos_agregar'),

]