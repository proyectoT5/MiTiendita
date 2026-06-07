from django.urls import path
from . import views

urlpatterns = [
    
    # --- Login y Logout ---
    path('login/', views.login_sql_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    
    # --- Gestión de Usuarios ---
    
    # 1. LISTA
    path('usuarios/', views.usuarios_lista_view, name='usuarios_lista'),
    
    # 2. AGREGAR
    path('usuarios/agregar/', views.usuarios_agregar_view, name='usuario_agregar'),
    
    # 3. EDITAR (Aquí estaba el error: cambiamos id_usu por id_usuario)
    path('usuarios/editar/<int:id_usuario>/', views.usuarios_editar_view, name='usuario_editar'),
    
    # 4. ELIMINAR (Aquí también: id_usuario)
    path('usuarios/eliminar/<int:id_usuario>/', views.usuarios_eliminar_view, name='usuario_eliminar'),
    
    # 5. REACTIVAR (Aquí también: id_usuario)
    path('usuarios/reactivar/<int:id_usuario>/', views.usuarios_reactivar_view, name='usuario_reactivar'),
    path('verificar-otp/', views.verificar_otp_view, name='verificar_otp'),
    path('recuperar-password/', views.recuperar_password_view, name='recuperar_password'),
    path('usuarios/restablecer-password/', views.restablecer_password_view, name='restablecer_password'),
    

]