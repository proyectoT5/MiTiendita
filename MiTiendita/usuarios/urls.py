from django.urls import path
from . import views

urlpatterns = [
    # Login/Logout
    path('login/', views.login_sql_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    
    # Gestión de Usuarios (CRUD)
    path('usuarios/', views.usuarios_lista_view, name='usuarios_lista'),
    path('usuarios/agregar/', views.usuarios_agregar_view, name='usuarios_agregar'),
    path('usuarios/editar/<int:id_usu>/', views.usuarios_editar_view, name='usuarios_editar'),
    path('usuarios/eliminar/<int:id_usu>/', views.usuarios_eliminar_view, name='usuarios_eliminar'),
    path('usuarios/reactivar/<int:id_usu>/', views.usuarios_reactivar_view, name='usuarios_reactivar'),
]