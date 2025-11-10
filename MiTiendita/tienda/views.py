# tienda/views.py
from django.shortcuts import render, redirect
from django.db import connection,transaction
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
def dictfetchall(cursor):
    "Return all rows from a cursor as a dict"
    columns = [col[0] for col in cursor.description]
    return [
        dict(zip(columns, row))
        for row in cursor.fetchall()
    ]

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

@login_requerido
def productos_eliminar_view(request, id_prod):
    """
    Recibe un ID de producto desde la URL y lo elimina.
    """
    
    # ¡Importante! Esta es una acción destructiva.
    # Más adelante te recomiendo poner un modal de confirmación.
    
    try:
        with connection.cursor() as cursor:
            # 1. Hacemos la consulta SQL DELETE
            sql_query = "DELETE FROM Productos WHERE Id_Producto = %s"
            cursor.execute(sql_query, [id_prod])
            
            # 2. Verificamos si se borró algo
            if cursor.rowcount == 0:
                # Esto pasa si el producto ya no existía
                messages.error(request, f"No se encontró el producto con ID {id_prod}.")
            else:
                messages.success(request, f"¡Producto (ID {id_prod}) eliminado con éxito!")
                
    except Exception as e:
        # --- ¡MANEJO DE ERROR CLAVE! ---
        # Si el producto está en una Factura, SQL Server dará un
        # error de "FOREIGN KEY constraint" y no te dejará borrarlo.
        error_str = str(e)
        if "FOREIGN KEY constraint" in error_str:
            messages.error(request, f"¡Error! No se puede eliminar el producto (ID {id_prod}) porque ya está en una factura registrada.")
        else:
            messages.error(request, f"Error al eliminar el producto: {e}")

    # 3. Al final, siempre regresamos a la lista de productos
    return redirect('productos_lista')


# --- ¡PEGUE 2: AGREGA ESTA NUEVA VISTA AL FINAL! ---
@login_requerido
def productos_editar_view(request, id_prod):
    """
    Esta vista hace 2 varas:
    1. (GET) Muestra el formulario con los datos del producto.
    2. (POST) Guarda los cambios en la base de datos.
    """
    
    # --- Lógica para GUARDAR los cambios (POST) ---
    if request.method == 'POST':
        # 1. Jalamos todos los datos del formulario
        prod_nombre = request.POST.get('Nombre')
        prod_precio = request.POST.get('PrecioVenta')
        prod_cantidad = request.POST.get('Cantidad')
        prod_stock = request.POST.get('StockMinimo')
        
        # Jalamos la ruta de la foto que ya estaba (desde un input oculto)
        ruta_db_para_foto = request.POST.get('rutaFotoActual') 

        # 2. Revisamos si subió una foto NUEVA
        if 'foto_del_producto' in request.FILES:
            archivo_foto = request.FILES['foto_del_producto']
            ruta_para_guardar = os.path.join(
                settings.BASE_DIR, 'Imagenes', archivo_foto.name
            )
            try:
                # Guardamos la foto nueva
                with open(ruta_para_guardar, 'wb+') as destination:
                    for chunk in archivo_foto.chunks():
                        destination.write(chunk)
                # Actualizamos la ruta para la BD
                ruta_db_para_foto = f"/static/{archivo_foto.name}"
            except Exception as e:
                messages.error(request, f"Error al guardar la nueva imagen: {e}")

        # 3. Creamos la consulta SQL UPDATE
        sql_query = """
            UPDATE Productos
            SET Nombre = %s, 
                PrecioVenta = %s, 
                Cantidad = %s, 
                StockMinimo = %s, 
                rutaFoto = %s
            WHERE Id_Producto = %s
        """
        params = [
            prod_nombre, prod_precio, prod_cantidad, 
            prod_stock, ruta_db_para_foto, id_prod # id_prod es el último
        ]

        try:
            with connection.cursor() as cursor:
                cursor.execute(sql_query, params)
            
            messages.success(request, f"¡Producto (ID: {id_prod}) actualizado con éxito!")
            return redirect('productos_lista') # De vuelta a la lista
        
        except Exception as e:
            messages.error(request, f"Error al actualizar el producto: {e}")

    # --- Lógica para MOSTRAR el formulario (GET) ---
    # (Si no es POST, hacemos esto)
    try:
        with connection.cursor() as cursor:
            # 1. Buscamos el producto por su ID
            sql_query = "SELECT * FROM Productos WHERE Id_Producto = %s"
            cursor.execute(sql_query, [id_prod])
            
            # Usamos la función 'dictfetchall' que movimos arriba
            producto_data = dictfetchall(cursor)
            
            if not producto_data:
                messages.error(request, f"No se encontró el producto con ID {id_prod}.")
                return redirect('productos_lista')
            
            producto = producto_data[0] # Agarramos el primer resultado

    except Exception as e:
        messages.error(request, f"Error al cargar el producto: {e}")
        return redirect('productos_lista')

    # 2. Mandamos los datos del producto al HTML
    context = {
        'nombre_usuario': request.session.get('user_nombre'),
        'rol_usuario': request.session.get('user_rol'),
        'producto': producto, # ¡La información para rellenar el form!
    }
    
    # 3. Renderizamos la plantilla de EDICIÓN
    return render(request, 'tienda/productos_editar.html', context)

@login_requerido
def clientes_view(request):
    
    # --- Lógica de Búsqueda (Filtro) ---
    search_query = request.GET.get('q', '') # 'q' será el 'name' de tu barra de búsqueda
    
    try:
        with connection.cursor() as cursor:
            if search_query:
                # Si hay búsqueda, buscamos por Nombre O Apellido
                sql_query = """
                    SELECT
                        C.Id_Cliente, C.Nombre, C.Apellido,
                        -- Esta función junta todos los teléfonos en un solo texto
                        STRING_AGG(CT.numero_telefono_C, ', ') AS Telefonos
                    FROM
                        Clientes C
                    LEFT JOIN
                        ClienteTelefono CT ON C.Id_Cliente = CT.id_cliente
                    WHERE
                        C.Nombre LIKE %s OR C.Apellido LIKE %s
                    GROUP BY
                        C.Id_Cliente, C.Nombre, C.Apellido
                """
                # Buscamos en nombre y apellido
                params = [f'%{search_query}%', f'%{search_query}%']
                cursor.execute(sql_query, params)
            else:
                # Si no hay búsqueda, traemos todos los clientes
                sql_query = """
                    SELECT
                        C.Id_Cliente, C.Nombre, C.Apellido,
                        STRING_AGG(CT.numero_telefono_C, ', ') AS Telefonos
                    FROM
                        Clientes C
                    LEFT JOIN
                        ClienteTelefono CT ON C.Id_Cliente = CT.id_cliente
                    GROUP BY
                        C.Id_Cliente, C.Nombre, C.Apellido
                """
                cursor.execute(sql_query)
            
            # Usamos la "herramienta" global
            clientes = dictfetchall(cursor)

    except Exception as e:
        clientes = []
        messages.error(request, f"Error al consultar clientes: {e}")
        print(f"Error al consultar clientes: {e}")

    context = {
        'nombre_usuario': request.session.get('user_nombre'),
        'rol_usuario': request.session.get('user_rol'),
        'clientes': clientes, # La lista de clientes
        'search_query': search_query, # Para que el texto se quede en la barra
    }
    return render(request, 'tienda/clientes.html', context)

@login_requerido
def clientes_agregar_view(request):
    if request.method == 'POST':
        cli_id = request.POST.get('Id_Cliente')
        cli_nombre = request.POST.get('Nombre')
        cli_apellido = request.POST.get('Apellido')
        cli_tel = request.POST.get('numero_telefono_C')

        try:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    # 🔹 Inserta el cliente
                    sql_cliente = """
                        INSERT INTO Clientes (Id_Cliente, Nombre, Apellido)
                        VALUES (%s, %s, %s)
                    """
                    cursor.execute(sql_cliente, [cli_id, cli_nombre, cli_apellido])

                    # 🔹 Inserta el teléfono si lo hay
                    if cli_tel:
                        cursor.execute("SELECT ISNULL(MAX(id_telefonoCli), 0) FROM ClienteTelefono")
                        new_id_tel = cursor.fetchone()[0] + 1

                        sql_telefono = """
                            INSERT INTO ClienteTelefono (id_telefonoCli, id_cliente, numero_telefono_C)
                            VALUES (%s, %s, %s)
                        """
                        cursor.execute(sql_telefono, [new_id_tel, cli_id, cli_tel])

                messages.success(request, f"¡Cliente '{cli_nombre} {cli_apellido}' agregado con éxito!")
                return redirect('clientes_lista')

        except Exception as e:
            messages.error(request, f"Error al agregar el cliente: {e}")

    context = {
        'nombre_usuario': request.session.get('user_nombre'),
        'rol_usuario': request.session.get('user_rol'),
    }
    return render(request, 'tienda/clientes_agregar.html', context)

@login_requerido
def clientes_eliminar_view(request, id_cli):
    """
    Elimina un cliente y sus teléfonos asociados,
    solo si no tiene facturas.
    """
    try:
        # Usamos la transacción atómica de Django
        with transaction.atomic():
            with connection.cursor() as cursor:
                
                # 1. Primero, borramos los "hijos" (los teléfonos)
                sql_telefonos = "DELETE FROM ClienteTelefono WHERE id_cliente = %s"
                cursor.execute(sql_telefonos, [id_cli])
                
                # 2. Segundo, borramos el "padre" (el cliente)
                sql_cliente = "DELETE FROM Clientes WHERE Id_Cliente = %s"
                cursor.execute(sql_cliente, [id_cli])
        
        messages.success(request, f"¡Cliente (ID {id_cli}) eliminado con éxito!")
    
    except Exception as e:
        # 3. ¡Manejo de Error!
        #    Si el 'DELETE' del cliente falla (Paso 2),
        #    es 99% seguro que es por una factura.
        error_str = str(e)
        if "FOREIGN KEY constraint" in error_str and "Factura" in error_str:
            messages.error(request, f"¡Error! No se puede eliminar el cliente (ID {id_cli}) porque ya tiene facturas registradas.")
        else:
            messages.error(request, f"Error al eliminar el cliente: {e}")

    # 4. Al final, siempre regresamos a la lista
    return redirect('clientes_lista')