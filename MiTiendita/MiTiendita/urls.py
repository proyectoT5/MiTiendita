from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views


from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views

urlpatterns = [
    path('admin/', admin.site.urls),

    # 1. PÁGINA PARA PEDIR EL CORREO (Tu formulario bonito)
    path('recuperar/', 
         auth_views.PasswordResetView.as_view(
             template_name='tienda/password_reset_form.html',
             html_email_template_name='registration/password_reset_email_html.html'
         ), 
         name='password_reset'),

    # 2. PÁGINA DE "¡CORREO ENVIADO!" (ESTA ES LA QUE FALLABA)
    # Al ponerla aquí, la obligamos a usar tu archivo movido a la carpeta 'tienda'
    path('accounts/password_reset/done/', 
         auth_views.PasswordResetDoneView.as_view(
             template_name='tienda/password_reset_done.html'
         ), 
         name='password_reset_done'),

    path('accounts/reset/<uidb64>/<token>/', 
         auth_views.PasswordResetConfirmView.as_view(
             template_name='tienda/password_reset_confirm.html'
         ), 
         name='password_reset_confirm'),

    # 4. PANTALLA FINAL DE ÉXITO
    path('accounts/reset/done/', 
         auth_views.PasswordResetCompleteView.as_view(
             template_name='tienda/password_reset_complete.html'
         ), 
         name='password_reset_complete'),

    # 3. Resto de las rutas de autenticación
    path('accounts/', include('django.contrib.auth.urls')),

    path('', include('usuarios.urls')), 
    path('', include('tienda.urls')),
]