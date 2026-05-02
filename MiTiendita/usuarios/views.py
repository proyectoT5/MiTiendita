from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.db.models import Q

# ==========================================
#             LOGIN / LOGOUT
# ==========================================

def login_sql_view(request):
    if request.method == 'POST':
        nombre = request.POST.get('username') 
        contra = request.POST.get('password')

        # 1. AUTENTICACIÓN REAL DE DJANGO
        # Esto verifica el usuario 'admin' que creamos en la consola
        user = authenticate(request, username=nombre, password=contra)

        if user is not None:
            if user.is_active:
                auth_login(request, user)
                
                # Guardamos datos en sesión para que tu HTML antiguo no falle
                request.session['user_id'] = user.id
                request.session['user_nombre'] = user.username
                request.session['user_rol'] = 'Admin' if user.is_superuser else 'Vendedor'
                
                return redirect('dashboard') # Asegúrate que esta URL exista
            else:
                messages.error(request, "Usuario desactivado.")
        else:
            messages.error(request, "Usuario o contraseña incorrectos.")
            
    return render(request, 'usuarios/login.html')

def logout_view(request):
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