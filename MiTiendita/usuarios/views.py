# usuarios/views.py
from django.shortcuts import render, redirect
from django.contrib import messages
from django.db import connection
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import User

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
        dato_login = request.POST.get('username') 
        password = request.POST.get('password')

        with connection.cursor() as cursor:
            # Buscamos por Nombre O Correo
            sql = """
                SELECT IdUsuario, Nombre, Rol, Contraseña 
                FROM Usuarios 
                WHERE (Nombre = %s OR Correo = %s) AND Activo = 1
            """
            cursor.execute(sql, [dato_login, dato_login])
            user = cursor.fetchone()
            
        if user:
            user_id, user_nombre, user_rol, hash_contrasena_db = user
            
            # --- LA SOLUCIÓN MÁGICA ---
            # 1. check_password: Revisa si es una contraseña segura (encriptada)
            # 2. password == hash_contrasena_db: Revisa si es la contraseña "123" tal cual la guardaste
            if check_password(password, hash_contrasena_db) or password == hash_contrasena_db:
                request.session['user_id'] = user_id
                request.session['user_nombre'] = user_nombre
                request.session['user_rol'] = user_rol
                return redirect('dashboard')
            else:
                messages.error(request, "Contraseña incorrecta.")
        else:
            messages.error(request, "Usuario no encontrado.")
            
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
    
    usuarios = []
    try:
        with connection.cursor() as cursor:
            # CORREGIDO: IdUsuario (sin guion)
            sql = "SELECT IdUsuario, Nombre, Rol, Activo, Correo FROM Usuarios WHERE Nombre LIKE %s"
            if not mostrar_desactivados:
                sql += " AND Activo = 1"
            
            cursor.execute(sql, [f'%{search_query}%'])
            usuarios = dictfetchall(cursor)
    except Exception as e:
        print(f"Error: {e}")

    return render(request, 'usuarios/usuarios_lista.html', {
        'usuarios': usuarios, 
        'search_query': search_query,
        'mostrando_desactivados': bool(mostrar_desactivados),
    })
# --- AGREGAR USUARIO ---
# Asegúrate de tener esto importado arriba (ya lo tenías en tu código):
# from django.contrib.auth.hashers import make_password

@admin_requerido
def usuarios_agregar_view(request):
    if request.method == 'POST':
        nombre = request.POST.get('nombre')
        contrasena = request.POST.get('contrasena')
        rol = request.POST.get('rol')
        correo = request.POST.get('correo')
        
        # Encriptar
        if contrasena:
            contrasena_encriptada = make_password(contrasena)
        else:
            contrasena_encriptada = "" 

        try:
            with connection.cursor() as cursor:
                
                # =======================================================
                # 🛡️ VALIDACIÓN NUEVA: ¿YA EXISTE EL CORREO?
                # =======================================================
                cursor.execute("SELECT COUNT(*) FROM Usuarios WHERE Correo = %s", [correo])
                existe = cursor.fetchone()[0]
                
                if existe > 0:
                    # Si ya existe, mandamos error y NO guardamos nada
                    messages.error(request, f"¡Error! El correo '{correo}' ya está siendo usado por otro usuario.")
                    return render(request, 'usuarios/usuarios_agregar.html')
                # =======================================================


                # Si el correo está libre, seguimos normal...
                cursor.execute("SELECT ISNULL(MAX(IdUsuario), 0) + 1 FROM Usuarios")
                new_id = cursor.fetchone()[0]
                
                # Insertar en SQL
                sql = "INSERT INTO Usuarios (IdUsuario, Nombre, Contraseña, Rol, Activo, Correo) VALUES (%s, %s, %s, %s, 1, %s)"
                cursor.execute(sql, [new_id, nombre, contrasena_encriptada, rol, correo])

                # Sincronizar con Django (El puente mágico)
                try:
                    if not User.objects.filter(username=nombre).exists():
                        User.objects.create_user(
                            username=nombre, 
                            email=correo, 
                            password=contrasena
                        )
                except Exception as e:
                    print(f"⚠️ Error sincronizando con Django: {e}")
                
            messages.success(request, f"Usuario {nombre} creado con éxito.")
            return redirect('usuarios_lista')
            
        except Exception as e:
            messages.error(request, f"Error al crear: {e}")

    return render(request, 'usuarios/usuarios_agregar.html')

@admin_requerido
def usuarios_editar_view(request, id_usuario): # 1. Recibe el nombre correcto
    
    # Buscamos al usuario en SQL
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM Usuarios WHERE IdUsuario = %s", [id_usuario])
        row = cursor.fetchone() # Guardamos el resultado en 'row' (fila)

    # Si no existe el usuario, evitamos errores feos
    if not row:
        messages.error(request, "Usuario no encontrado.")
        return redirect('usuarios_lista')

    # 2. EL TRADUCTOR MÁGICO (Convertimos la lista a Diccionario)
    # Esto soluciona el error amarillo de "NoReverseMatch"
    usuario = {
        'IdUsuario': row[0],
        'Nombre': row[1],
        'Contraseña': row[2],
        'Rol': row[3],
        'Activo': row[4],
        'Correo': row[6] if row[6] else "",
    }

    if request.method == 'POST':
        nombre = request.POST.get('nombre')
        contrasena = request.POST.get('contrasena')
        rol = request.POST.get('rol')
        correo = request.POST.get('correo')
        
        try:
            with connection.cursor() as cursor:
                # 🛡️ VALIDACIÓN ANTI-GEMELOS
                cursor.execute("""
                    SELECT COUNT(*) FROM Usuarios 
                    WHERE Correo = %s AND IdUsuario != %s
                """, [correo, id_usuario])
                
                if cursor.fetchone()[0] > 0:
                    messages.error(request, f"¡Error! El correo '{correo}' ya lo tiene otra persona.")
                    return render(request, 'usuarios/usuarios_editar.html', {'usuario': usuario})

                # ACTUALIZACIÓN EN SQL
                if contrasena:
                    clave_encriptada = make_password(contrasena)
                    sql = """
                        UPDATE Usuarios 
                        SET Nombre=%s, Contraseña=%s, Rol=%s, Correo=%s 
                        WHERE IdUsuario=%s
                    """
                    cursor.execute(sql, [nombre, clave_encriptada, rol, correo, id_usuario])
                    
                    # Sincronizar Django (Con clave nueva)
                    try:
                        u = User.objects.get(username=nombre)
                        u.email = correo
                        u.set_password(contrasena)
                        u.save()
                    except User.DoesNotExist:
                        # Si no existe, lo creamos
                        User.objects.create_user(username=nombre, email=correo, password=contrasena)
                else:
                    # Sin clave nueva
                    sql = "UPDATE Usuarios SET Nombre=%s, Rol=%s, Correo=%s WHERE IdUsuario=%s"
                    cursor.execute(sql, [nombre, rol, correo, id_usuario])

                    # Sincronizar Django (Solo correo)
                    try:
                        u = User.objects.get(username=nombre)
                        u.email = correo
                        u.save()
                    except User.DoesNotExist:
                        pass 

            messages.success(request, "Usuario actualizado correctamente.")
            return redirect('usuarios_lista')

        except Exception as e:
            messages.error(request, f"Error al actualizar: {e}")

    # Enviamos el diccionario 'usuario' traducido
    return render(request, 'usuarios/usuarios_editar.html', {'usuario': usuario})

@admin_requerido
def usuarios_eliminar_view(request, id_usuario):
    try:
        with connection.cursor() as cursor:
            # CORREGIDO: IdUsuario
            cursor.execute("UPDATE Usuarios SET Activo = 0 WHERE IdUsuario = %s", [id_usuario])
        messages.success(request, "Usuario desactivado.")
    except Exception as e:
        messages.error(request, f"Error: {e}")
    return redirect('usuarios_lista')
    

@admin_requerido
def usuarios_reactivar_view(request, id_usuario):
    try:
        with connection.cursor() as cursor:
            # CORREGIDO: IdUsuario
            cursor.execute("UPDATE Usuarios SET Activo = 1 WHERE IdUsuario = %s", [id_usuario])
        messages.success(request, "Usuario reactivado.")
    except Exception as e:
        messages.error(request, f"Error: {e}")
    return redirect('usuarios_lista')