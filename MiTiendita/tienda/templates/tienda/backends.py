from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
from django.db.models import Q

class EmailOrUsernameBackend(ModelBackend):
    """
    Autenticación personalizada para permitir iniciar sesión 
    usando correo electrónico o nombre de usuario.
    """
    def authenticate(self, request, username=None, password=None, **kwargs):
        User = get_user_model()
        try:
            # Buscamos un usuario cuyo 'username' O 'email' coincida con lo que escribió
            user = User.objects.get(Q(username__iexact=username) | Q(email__iexact=username))
        except User.DoesNotExist:
            return None
        except User.MultipleObjectsReturned:
            # Si hay varios usuarios con el mismo email (mala práctica, pero posible), retornamos el primero
            user = User.objects.filter(Q(username__iexact=username) | Q(email__iexact=username)).order_by('id').first()

        # Verificamos la contraseña y si el usuario puede iniciar sesión
        if user and user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
    
    # settings.py

AUTHENTICATION_BACKENDS = [
    'backends.py.backends.EmailOrUsernameBackend',  # Cambia 'core' por el nombre de tu app
    'django.contrib.auth.backends.ModelBackend', # Mantenemos el default por seguridad
]