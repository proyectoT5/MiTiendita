from . import views
from django.urls import path


urlpatterns = [
    path('',views.dashboard_view, name='dashboard'),
    path('productos/', views.productos_view, name='productos_lista'),
    path('productos/agregar/', views.productos_agregar_view, name='productos_agregar'),
    path('productos/eliminar/<int:id_prod>/', views.productos_eliminar_view, name='productos_eliminar'),
    path('productos/editar/<int:id_prod>/', views.productos_editar_view, name='productos_editar'),
    path('clientes/', views.clientes_view, name='clientes_lista'),

]
