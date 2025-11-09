# tienda/views.py
from django.shortcuts import render, redirect
from django.db import connection
from django.contrib import messages
from django.conf import settings 
import os

# --- Este es un "Decorador" ---
# Su trabajo es revisar si el usuario inició sesión.
# Si no, lo bota al login.
def login_requerido(view_func):
    def wrapper(request, *args, **kwargs):
        # Revisa si 'user_id' está en la sesión que guardamos al logearnos
        if 'user_id' not in request.session:
            return redirect('login') # Si no está, a la página de login
        
        # Si sí está, ejecuta la vista (ej: dashboard_view)
        return view_func(request, *args, **kwargs)
    return wrapper
# -------------------------------


@login_requerido
def dashboard_view(request):
    

    try:
        with connection.cursor() as cursor:
            # 1. Contar Clientes
            cursor.execute("SELECT COUNT(*) FROM Clientes")
            num_clientes = cursor.fetchone()[0]
            
            # 2. Contar Productos
            cursor.execute("SELECT COUNT(*) FROM Productos")
            num_productos = cursor.fetchone()[0]
            
            # 3. Contar Proveedores
            cursor.execute("SELECT COUNT(*) FROM Proveedores")
            num_proveedores = cursor.fetchone()[0]

    except Exception as e:
        # Si algo falla (ej: la tabla no existe)
        num_clientes = 0
        num_productos = 0
        num_proveedores = 0

        print(f"Error al contar con SQL: {e}") # Para ver el error en la consola

    # Preparamos el "contexto" para mandarlo al HTML
    context = {
        'nombre_usuario': request.session.get('user_nombre'),
        'rol_usuario': request.session.get('user_rol'),
        
        # Los números que contamos
        'total_clientes': num_clientes,
        'total_productos': num_productos,
        'total_proveedores': num_proveedores,

    }
    
    return render(request, 'tienda/dashboard.html', context)

@login_requerido
def productos_view(request):
    
    # Esta función transforma los resultados de SQL (tuplas)
    # en una lista de diccionarios (más fácil de usar en HTML)
    def dictfetchall(cursor):
        "Return all rows from a cursor as a dict"
        columns = [col[0] for col in cursor.description]
        return [
            dict(zip(columns, row))
            for row in cursor.fetchall()
        ]

    # --- Lógica de Búsqueda (Filtro) ---
    search_query = request.GET.get('q', '') # 'q' será el 'name' de tu barra de búsqueda
    
    try:
        with connection.cursor() as cursor:
            if search_query:
                # Si hay búsqueda, usamos LIKE para filtrar por nombre
                # [f'%{search_query}%'] es la forma segura de pasar el parámetro
                sql_query = """
                    SELECT Id_Producto, Nombre, PrecioVenta, Cantidad, StockMinimo 
                    FROM Productos 
                    WHERE Nombre LIKE %s
                """
                cursor.execute(sql_query, [f'%{search_query}%'])
            else:
                # Si no hay búsqueda, traemos todos los productos
                sql_query = """
                    SELECT Id_Producto, Nombre, PrecioVenta, Cantidad, StockMinimo 
                    FROM Productos
                """
                cursor.execute(sql_query)
            
            # Usamos la función 'dictfetchall' para obtener los resultados
            productos = dictfetchall(cursor)

    except Exception as e:
        productos = []
        print(f"Error al consultar productos: {e}")

    context = {
        'nombre_usuario': request.session.get('user_nombre'),
        'rol_usuario': request.session.get('user_rol'),
        'productos': productos, # La lista de productos (filtrada o completa)
        'search_query': search_query, # Para que el texto se quede en la barra
    }
    
    # Usaremos una nueva plantilla llamada 'productos.html'
    return render(request, 'tienda/productos.html', context)

@login_requerido
def productos_agregar_view(request):
    
    if request.method == 'POST':
        prod_id = request.POST.get('Id_Producto')
        prod_nombre = request.POST.get('Nombre')
        prod_precio = request.POST.get('PrecioVenta')
        prod_cantidad = request.POST.get('Cantidad')
        prod_stock = request.POST.get('StockMinimo')
        
        # --- LÓGICA DE LA FOTO (YA CORREGIDA) ---
        
        ruta_db_para_foto = '' # Vacía por defecto
        
        if 'foto_del_producto' in request.FILES:
            archivo_foto = request.FILES['foto_del_producto']
            
            # 1. Definimos la ruta para GUARDAR el archivo
            #    Ahora apunta a tu carpeta 'Imagenes'
            ruta_para_guardar = os.path.join(
                settings.BASE_DIR, 
                'Imagenes',  # <-- ¡CAMBIO AQUÍ!
                archivo_foto.name
            )
            
            # 2. Guardamos el archivo en el disco
            try:
                with open(ruta_para_guardar, 'wb+') as destination:
                    for chunk in archivo_foto.chunks():
                        destination.write(chunk)
                
                # 3. Creamos la ruta para la BASE DE DATOS
                #    Como 'Imagenes' es "static", la URL es '/static/' + nombre
                ruta_db_para_foto = f"/static/{archivo_foto.name}" # <-- ¡CAMBIO AQUÍ!
            
            except Exception as e:
                messages.error(request, f"Error al guardar la imagen: {e}")

        # 4. Creamos la consulta SQL INSERT
        sql_query = """
            INSERT INTO Productos (Id_Producto, Nombre, PrecioVenta, Cantidad, StockMinimo, rutaFoto)
            VALUES (%s, %s, %s, %s, %s, %s)
        """
        params = [prod_id, prod_nombre, prod_precio, prod_cantidad, prod_stock, ruta_db_para_foto]

        try:
            with connection.cursor() as cursor:
                cursor.execute(sql_query, params)
            
            messages.success(request, f"¡Producto '{prod_nombre}' agregado con éxito!")
            return redirect('productos_lista')
        
        except Exception as e:
            messages.error(request, f"Error al agregar el producto: {e}")

    # --- Lógica para MOSTRAR el formulario (GET) ---
    context = {
        'nombre_usuario': request.session.get('user_nombre'),
        'rol_usuario': request.session.get('user_rol'),
    }
    # Asegúrate de que la ruta de la plantilla esté correcta
    return render(request, 'tienda/productos_agregar.html', context)