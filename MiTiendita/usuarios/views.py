# usuarios/views.py
from django.shortcuts import render, redirect
from django.contrib import messages
from django.db import connection
from django.contrib.auth.hashers import check_password # ¡Importante para contraseñas seguras!

def login_sql_view(request):
    if request.method == 'POST':
        nombre = request.POST.get('username')
        password = request.POST.get('password')

        with connection.cursor() as cursor:
            # 1. Traemos al usuario SOLO por el nombre
            cursor.execute(
                "SELECT IdUsuario, Nombre, Rol, Contraseña FROM dbo.[Usuarios] WHERE Nombre = %s",
                [nombre]
            )
            user = cursor.fetchone()

        if user:
            # Desempaquetamos los datos
            user_id = user[0]
            user_nombre = user[1]
            user_rol = user[2]
            hash_contrasena_db = user[3] # El hash guardado en la BD

            # 2. Verificamos la contraseña en Python (¡NO EN SQL!)
            #    check_password compara el texto simple (password) con el hash (hash_contrasena_db)
            if check_password(password, hash_contrasena_db):
                
                # 3. Guardamos todo en la sesión (incluyendo el ROL)
                request.session['user_id'] = user_id
                request.session['user_nombre'] = user_nombre
                request.session['user_rol'] = user_rol # ¡Campo clave!
                
                messages.success(request, f"Bienvenido {user_nombre} 👋")
                
                # 4. Redirigimos al 'name' de la URL del dashboard (NO al .html)
                return redirect('dashboard') # Asumiendo que tu dashboard se llama 'dashboard'
            else:
                messages.error(request, "Usuario o contraseña inválidos.")
        else:
            messages.error(request, "Usuario o contraseña inválidos.")

    return render(request, 'login.html')

def logout_view(request):
    """
    Limpia la sesión del usuario y lo redirige al login.
    """
    try:
        # Borra las llaves de la sesión que creamos en el login
        del request.session['user_id']
        del request.session['user_nombre']
        del request.session['user_rol']
    except KeyError:
        # Si ya estaba deslogueado, no hace nada
        pass
    
    messages.info(request, "Has cerrado sesión exitosamente.")
    # Redirige de vuelta a la página de login
    return redirect('login')