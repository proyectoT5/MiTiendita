
from django.shortcuts import render, redirect
from django.contrib import messages
from django.db import connection

def login_sql_view(request):
    if request.method == 'POST':
        nombre = request.POST.get('username')
        password = request.POST.get('password')

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT IdUsuario, Nombre FROM dbo.[Usuarios] WHERE Nombre = %s AND Contraseña = %s",
                [nombre, password]
            )
            user = cursor.fetchone()

        if user:
            request.session['user_id'] = user[0]
            request.session['user_nombre'] = user[1]
            messages.success(request, f"Bienvenido {user[1]} 👋")
            return redirect('base.html')  # usa la URL directa por ahora
        else:
            messages.error(request, "Usuario o contraseña inválidos.")

    return render(request, 'login.html')
