# usuarios/views.py
from django.shortcuts import render, redirect
from django.contrib import messages
from django.db import connection
from django.contrib.auth.hashers import check_password, make_password

# --- HERRAMIENTA GLOBAL ---
def dictfetchall(cursor):
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]

# --- DECORADOR: SOLO ADMIN ---
def admin_requerido(view_func):
    def wrapper(request, *args, **kwargs):
        if 'user_id' not in request.session:
            return redirect('login')
        
        if request.session.get('user_rol') != 'Admin':
            messages.error(request, "Acceso denegado.")
            return redirect('dashboard') 
        
        return view_func(request, *args, **kwargs)
    return wrapper

# ==========================================
#              LOGIN / LOGOUT
# ==========================================

def login_sql_view(request):
    if request.method == 'POST':
        nombre = request.POST.get('username')
        password = request.POST.get('password')
        with connection.cursor() as cursor:
            cursor.execute("SELECT IdUsuario, Nombre, Rol, Contraseña FROM Usuarios WHERE Nombre = %s AND Activo = 1", [nombre])
            user = cursor.fetchone()
        if user:
            user_id, user_nombre, user_rol, hash_contrasena_db = user
            if check_password(password, hash_contrasena_db):
                request.session['user_id'] = user_id
                request.session['user_nombre'] = user_nombre
                request.session['user_rol'] = user_rol
                # Sin mensaje aquí para que no estorbe al entrar
                return redirect('dashboard')
            else:
                messages.error(request, "Contraseña incorrecta.")
        else:
            messages.error(request, "Usuario no encontrado o desactivado.")
            
    return render(request, 'usuarios/login.html')

def logout_view(request):
    try:
        del request.session['user_id']
        del request.session['user_nombre']
        del request.session['user_rol']
    except KeyError: pass
    return redirect('login')

# ==========================================
#        CRUD DE USUARIOS
# ==========================================

@admin_requerido
def usuarios_lista_view(request):
    search_query = request.GET.get('q', '')
    mostrar_desactivados = request.GET.get('mostrar_desactivados')
    try:
        with connection.cursor() as cursor:
            where_clause = "WHERE (Nombre LIKE %s)"
            params = [f'%{search_query}%']
            if not mostrar_desactivados: where_clause += " AND Activo = 1"
            sql = f"SELECT IdUsuario, Nombre, Rol, Activo FROM Usuarios {where_clause} ORDER BY Nombre"
            cursor.execute(sql, params)
            usuarios = dictfetchall(cursor)
    except Exception as e:
        usuarios = []
        messages.error(request, f"Error: {e}")
    return render(request, 'usuarios/usuarios_lista.html', {'usuarios': usuarios, 'search_query': search_query, 'mostrando_desactivados': bool(mostrar_desactivados)})

@admin_requerido
def usuarios_agregar_view(request):
    if request.method == 'POST':
        id_usu = request.POST.get('IdUsuario')
        nombre = request.POST.get('Nombre')
        rol = request.POST.get('Rol')
        password_raw = request.POST.get('Password')
        password_hash = make_password(password_raw)
        try:
            with connection.cursor() as cursor:
                # Validar ID repetido
                cursor.execute("SELECT COUNT(*) FROM Usuarios WHERE IdUsuario = %s", [id_usu])
                if cursor.fetchone()[0] > 0:
                    messages.error(request, "El ID de usuario ya existe.")
                    return render(request, 'usuarios/usuarios_agregar.html')

                sql = "INSERT INTO Usuarios (IdUsuario, Nombre, Contraseña, Rol, Activo) VALUES (%s, %s, %s, %s, 1)"
                cursor.execute(sql, [id_usu, nombre, password_hash, rol])
            
            # ¡AQUÍ ESTÁ EL MENSAJE!
            messages.success(request, f"Usuario '{nombre}' creado con éxito.")
            return redirect('usuarios_lista')
        except Exception as e: messages.error(request, f"Error: {e}")
    return render(request, 'usuarios/usuarios_agregar.html')

@admin_requerido
def usuarios_editar_view(request, id_usu):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM Usuarios WHERE IdUsuario = %s", [id_usu])
            data = dictfetchall(cursor)
            if not data: return redirect('usuarios_lista')
            usuario = data[0]
    except: return redirect('usuarios_lista')

    if request.method == 'POST':
        nombre = request.POST.get('Nombre')
        rol = request.POST.get('Rol')
        password_raw = request.POST.get('Password')
        try:
            with connection.cursor() as cursor:
                if password_raw:
                    password_hash = make_password(password_raw)
                    cursor.execute("UPDATE Usuarios SET Nombre=%s, Rol=%s, Contraseña=%s WHERE IdUsuario=%s", [nombre, rol, password_hash, id_usu])
                else:
                    cursor.execute("UPDATE Usuarios SET Nombre=%s, Rol=%s WHERE IdUsuario=%s", [nombre, rol, id_usu])
            
            # ¡AQUÍ ESTÁ EL MENSAJE!
            messages.success(request, "Usuario actualizado correctamente.")
            return redirect('usuarios_lista')
        except Exception as e: messages.error(request, f"Error: {e}")

    return render(request, 'usuarios/usuarios_editar.html', {'usuario': usuario})

@admin_requerido
def usuarios_eliminar_view(request, id_usu):
    if str(id_usu) == str(request.session.get('user_id')):
        messages.error(request, "¡No podés desactivarte a vos mismo!")
        return redirect('usuarios_lista')
    try:
        with connection.cursor() as cursor:
            cursor.execute("UPDATE Usuarios SET Activo = 0 WHERE IdUsuario = %s", [id_usu])
            # ¡AQUÍ ESTÁ EL MENSAJE!
            messages.success(request, "Usuario desactivado.")
    except Exception as e: messages.error(request, f"Error: {e}")
    return redirect('usuarios_lista')

@admin_requerido
def usuarios_reactivar_view(request, id_usu):
    try:
        with connection.cursor() as cursor:
            cursor.execute("UPDATE Usuarios SET Activo = 1 WHERE IdUsuario = %s", [id_usu])
            # ¡AQUÍ ESTÁ EL MENSAJE!
            messages.success(request, "Usuario reactivado.")
    except Exception as e: messages.error(request, f"Error: {e}")
    return redirect('usuarios_lista')