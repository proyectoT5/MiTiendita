from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from .utils import validar_otp  # o donde pongas la lógica
from .utils import generar_otp
import pyotp
import logging

logger = logging.getLogger('miapp')
# ==========================================
#             LOGIN / LOGOUT
# ==========================================
def login_sql_view(request):
    if request.method == 'POST':
        nombre = request.POST.get('username') 
        contra = request.POST.get('password')

        user = authenticate(request, username=nombre, password=contra)

        if user is not None:
            if user.is_active:
                
                # ✅ LOGIN NORMAL (como antes)
                auth_login(request, user)
                logger.info(f"Inicio de sesión exitoso: {nombre}")

                # compatibilidad con tu sistema actual
                request.session['user_id'] = user.id
                request.session['user_nombre'] = user.username
                request.session['user_rol'] = 'Admin' if user.is_superuser else 'Vendedor'

                return redirect('dashboard')

            else:
                messages.error(request, "Usuario desactivado.")
                logger.warning(f"Usuario desactivado intentó login: {nombre}")
        else:
            messages.error(request, "Usuario o contraseña incorrectos.")
            logger.error(f"Intento de login fallido: {nombre}")
            
    return render(request, 'usuarios/login.html')


def logout_view(request):
    if request.user.is_authenticated:
        logger.info(f"Cierre de sesión: {request.user.username}")

    auth_logout(request) # Limpieza total de sesión
    try:
        del request.session['user_id']
        del request.session['user_nombre']
        del request.session['user_rol']
       
    except KeyError:
        pass
    return redirect('login')

# ==========================================
#             DECORADOR CASERO
# ==========================================
def admin_requerido(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if not request.user.is_superuser:
            messages.error(request, "Acceso denegado. Solo Admin.")
            return redirect('dashboard') 
        return view_func(request, *args, **kwargs)
    return wrapper

# ==========================================
#          CRUD DE USUARIOS (ADAPTADO)
# ==========================================

@admin_requerido
def usuarios_lista_view(request):
    search_query = request.GET.get('q', '')
    mostrar_desactivados = request.GET.get('mostrar_desactivados')
    
    # Consulta usando el ORM de Django (No SQL manual)
    users_qs = User.objects.all().order_by('id')
    
    if search_query:
        users_qs = users_qs.filter(
            Q(username__icontains=search_query) | 
            Q(email__icontains=search_query)
        )
    
    if not mostrar_desactivados:
        users_qs = users_qs.filter(is_active=True)

    # --- ADAPTADOR DE DICCIONARIOS ---
    # Convertimos los objetos de Django al formato que espera tu HTML
    # (IdUsuario, Nombre, Rol, Activo, etc.)
    usuarios_lista = []
    for u in users_qs:
        usuarios_lista.append({
            'IdUsuario': u.id,
            'Nombre': u.username,
            'Rol': 'Admin' if u.is_superuser else 'Vendedor',
            'Activo': 1 if u.is_active else 0,
            'Correo': u.email,
        })

    return render(request, 'usuarios/usuarios_lista.html', {
        'usuarios': usuarios_lista, 
        'search_query': search_query,
        'mostrando_desactivados': bool(mostrar_desactivados),
    })

@admin_requerido
def usuarios_agregar_view(request):
    if request.method == 'POST':
        nombre = request.POST.get('nombre')
        contra = request.POST.get('contrasena')
        rol = request.POST.get('rol') # Esperamos 'Admin' o 'Vendedor'
        correo = request.POST.get('correo')
        
        # Validación de duplicados
        if User.objects.filter(username=nombre).exists():
            messages.error(request, f"El usuario {nombre} ya existe.")
            return render(request, 'usuarios/usuarios_agregar.html')

        try:
            # Crear usuario en Django
            nuevo_usuario = User.objects.create_user(
                username=nombre,
                email=correo,
                password=contra
            )
            
            # Asignar Rol
            if rol == 'Admin':
                nuevo_usuario.is_superuser = True
                nuevo_usuario.is_staff = True
            
            nuevo_usuario.save()
            
            messages.success(request, f"Usuario {nombre} creado con éxito.")
            return redirect('usuarios_lista')
            
        except Exception as e:
            messages.error(request, f"Error al crear: {e}")

    return render(request, 'usuarios/usuarios_agregar.html')

@admin_requerido
def usuarios_editar_view(request, id_usuario):
    # Obtener usuario real o dar error 404
    u = get_object_or_404(User, pk=id_usuario)

    # Adaptar para el template
    usuario_dict = {
        'IdUsuario': u.id,
        'Nombre': u.username,
        'Rol': 'Admin' if u.is_superuser else 'Vendedor',
        'Correo': u.email,
        'Activo': 1 if u.is_active else 0,
    }

    if request.method == 'POST':
        nombre = request.POST.get('nombre')
        contra = request.POST.get('contrasena')
        rol = request.POST.get('rol')
        correo = request.POST.get('correo')
        
        try:
            # Actualizar datos básicos
            u.username = nombre
            u.email = correo
            
            # Actualizar Rol
            if rol == 'Admin':
                u.is_superuser = True
                u.is_staff = True
            else:
                u.is_superuser = False
                u.is_staff = False
            
            # Actualizar contraseña SOLO si escribieron algo
            if contra and len(contra.strip()) > 0:
                u.set_password(contra)
            
            u.save()
            messages.success(request, "Usuario actualizado correctamente.")
            return redirect('usuarios_lista')

        except Exception as e:
            messages.error(request, f"Error al actualizar: {e}")

    return render(request, 'usuarios/usuarios_editar.html', {'usuario': usuario_dict})

@admin_requerido
def usuarios_eliminar_view(request, id_usuario):
    try:
        u = User.objects.get(pk=id_usuario)
        u.is_active = False # Desactivar en lugar de borrar
        u.save()
        messages.success(request, "Usuario desactivado.")
    except User.DoesNotExist:
        messages.error(request, "Usuario no encontrado.")
    return redirect('usuarios_lista')

@admin_requerido
def usuarios_reactivar_view(request, id_usuario):
    try:
        u = User.objects.get(pk=id_usuario)
        u.is_active = True
        u.save()
        messages.success(request, "Usuario reactivado.")
    except User.DoesNotExist:
        messages.error(request, "Usuario no encontrado.")
    return redirect('usuarios_lista')

# ==========================================
#         SISTEMA DE AUTENTICACIÓN OTP
# ==========================================
import base64
import hashlib

def obtener_secreto_persistente_usuario(user):
    """
    Genera una llave secreta en Base32 única para cada usuario.
    No cambia entre intentos de recuperación, lo que evita que el QR se desfase
    con la aplicación de Google Authenticator.
    """
    # Creamos un hash único usando el ID del usuario y su fecha de registro o username
    semilla = f"MiTienditaSecret-{user.id}-{user.username}"
    hash_bytes = hashlib.sha256(semilla.encode('utf-8')).digest()
    
    # pyotp necesita una cadena en Base32 (letras de la A a la Z y números del 2 al 7)
    secreto_b32 = base64.b32encode(hash_bytes).decode('utf-8').replace('=', '')[:32]
    return secreto_b32

def recuperar_password_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')

        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            messages.error(request, "El usuario ingresado no existe.")
            return render(request, 'usuarios/recuperar_password.html')

        # ✅ CORREGIDO: En lugar de random_base32(), usamos una llave fija por usuario
        secret = obtener_secreto_persistente_usuario(user)

        # Guardamos en la sesión para la verificación posterior
        request.session['otp_secret'] = secret
        request.session['user_id_temp'] = user.id
        request.session.modified = True

        totp = pyotp.TOTP(secret)
        uri = totp.provisioning_uri(name=user.username, issuer_name="MiTiendita")

        return render(request, 'usuarios/otp_qr.html', {'uri': uri})

    return render(request, 'usuarios/recuperar_password.html')


def validar_otp(request, codigo):
    secret = request.session.get('otp_secret')
    if not secret:
        return False
    
    totp = pyotp.TOTP(secret)
    # Agregamos una ventana de tolerancia de 1 paso (30 segundos antes/después) 
    # por si el reloj del celular del usuario está ligeramente desincronizado
    return totp.verify(codigo, valid_window=1)


def verificar_otp_view(request):
    if request.method == 'POST':
        codigo = request.POST.get('otp')
        user_id = request.session.get('user_id_temp')

        if not user_id:
            messages.error(request, "La sesión de verificación expiró. Inicia de nuevo.")
            return redirect('login')

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return redirect('login')

        if validar_otp(request, codigo):
            # ✅ LOGIN AUTOMÁTICO COMPATIBLE
            auth_login(request, user)

            request.session['user_id'] = user.id
            request.session['user_nombre'] = user.username
            request.session['user_rol'] = 'Admin' if user.is_superuser else 'Vendedor'

            try:
                del request.session['user_id_temp']
                del request.session['otp_secret']
            except KeyError:
                pass

            messages.success(request, f"¡Bienvenido, {user.username}!")
            return redirect('dashboard')
        else:
            messages.error(request, "Código OTP inválido. Verifica tu aplicación.")
            
            # Re-renderizamos manteniendo la consistencia de la URI
            secret = request.session.get('otp_secret')
            totp = pyotp.TOTP(secret)
            uri = totp.provisioning_uri(name=user.username, issuer_name="MiTiendita")
            return render(request, 'usuarios/otp_qr.html', {'uri': uri})

    return redirect('login')