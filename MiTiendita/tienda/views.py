# tienda/views.py
from django.shortcuts import render, redirect
from django.db import connection, transaction
from django.contrib import messages
from django.conf import settings 
from django.http import JsonResponse 
from django.template.loader import render_to_string
import os
import datetime 
from decimal import Decimal 
import json

# --- DECORADORES ---
def login_requerido(view_func):
    def wrapper(request, *args, **kwargs):
        if 'user_id' not in request.session:
            return redirect('login') 
        return view_func(request, *args, **kwargs)
    return wrapper

def admin_requerido(view_func):
    def wrapper(request, *args, **kwargs):
        if 'user_id' not in request.session:
            return redirect('login')
        if request.session.get('user_rol') != 'Admin':
            messages.error(request, "¡Acceso denegado! Solo el Admin puede hacer esto.")
            return redirect('dashboard') 
        return view_func(request, *args, **kwargs)
    return wrapper

# --- HERRAMIENTA GLOBAL ---
def dictfetchall(cursor):
    "Return all rows from a cursor as a dict"
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]

# ==========================================
#              DASHBOARD & REPORTES
# ==========================================
@login_requerido
def dashboard_view(request):
    # Inicializamos variables por si falla la BD
    num_clientes = 0
    num_productos = 0
    num_proveedores = 0
    top5_data = []
    productos_bajos = [] # ¡ESTA ES LA NUEVA!

    try:
        with connection.cursor() as cursor:
            # 1. Contadores
            cursor.execute("SELECT COUNT(*) FROM Clientes WHERE Activo = 1 AND EsOcasional = 0")
            num_clientes = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM Productos WHERE Activo = 1")
            num_productos = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM Proveedores WHERE Activo = 1")
            num_proveedores = cursor.fetchone()[0]
            
            # 2. Gráfica Top 5
            sql_top5 = """
                SELECT TOP 5 P.Nombre, SUM(D.cantidad) as TotalVendido
                FROM DetalleFactura D
                JOIN Productos P ON D.Id_Producto = P.Id_Producto
                GROUP BY P.Nombre
                ORDER BY TotalVendido DESC
            """
            cursor.execute(sql_top5)
            top5_data = dictfetchall(cursor)

            # 3. ¡ALERTA DE STOCK BAJO! (NUEVO)
            # Busca productos donde la Cantidad actual sea menor o igual al Mínimo
            sql_stock = """
                SELECT Id_Producto, Nombre, Cantidad, StockMinimo 
                FROM Productos 
                WHERE Cantidad <= StockMinimo AND Activo = 1
                ORDER BY Cantidad ASC
            """
            cursor.execute(sql_stock)
            productos_bajos = dictfetchall(cursor)
            
    except Exception as e:
        print(f"Error dashboard: {e}")
        
    labels = [item['Nombre'] for item in top5_data]
    data = [item['TotalVendido'] for item in top5_data]

    context = {
        'nombre_usuario': request.session.get('user_nombre'),
        'rol_usuario': request.session.get('user_rol'),
        'total_clientes': num_clientes,
        'total_productos': num_productos,
        'total_proveedores': num_proveedores,
        'chart_labels': json.dumps(labels),
        'chart_data': json.dumps(data),
        'productos_bajos': productos_bajos, # Mandamos la lista de alertas al HTML
    }
    return render(request, 'tienda/dashboard.html', context)

@login_requerido
def reportes_view(request):
    rol = request.session.get('user_rol')
    user_id = request.session.get('user_id')
    
    # Estructura de datos para guardar Cantidad y Dinero
    data_reporte = {
        'hoy': {'cant': 0, 'total': 0},
        'semana': {'cant': 0, 'total': 0},
        'mes': {'cant': 0, 'total': 0}
    }
    
    chart_labels = []
    chart_data = []

    try:
        with connection.cursor() as cursor:
            # --- FILTRO SEGÚN ROL ---
            # Si es Admin, no filtramos por usuario. Si es Empleado, sí.
            filtro_user = "" 
            params_base = []
            
            if rol != 'Admin':
                filtro_user = "AND Id_Usuario = %s"
                params_base = [user_id]

            # 1. HOY
            sql_hoy = f"SELECT COUNT(*), ISNULL(SUM(Total), 0) FROM Factura WHERE CAST(FechaHora AS DATE) = CAST(GETDATE() AS DATE) {filtro_user}"
            cursor.execute(sql_hoy, params_base)
            row = cursor.fetchone()
            data_reporte['hoy']['cant'] = row[0]
            data_reporte['hoy']['total'] = row[1]

            # 2. SEMANA
            sql_semana = f"SELECT COUNT(*), ISNULL(SUM(Total), 0) FROM Factura WHERE DATEPART(ww, FechaHora) = DATEPART(ww, GETDATE()) AND DATEPART(yy, FechaHora) = DATEPART(yy, GETDATE()) {filtro_user}"
            cursor.execute(sql_semana, params_base)
            row = cursor.fetchone()
            data_reporte['semana']['cant'] = row[0]
            data_reporte['semana']['total'] = row[1]

            # 3. MES
            sql_mes = f"SELECT COUNT(*), ISNULL(SUM(Total), 0) FROM Factura WHERE MONTH(FechaHora) = MONTH(GETDATE()) AND YEAR(FechaHora) = YEAR(GETDATE()) {filtro_user}"
            cursor.execute(sql_mes, params_base)
            row = cursor.fetchone()
            data_reporte['mes']['cant'] = row[0]
            data_reporte['mes']['total'] = row[1]

            # 4. GRÁFICA (Últimos 7 días)
            # Nota: Aquí hay que tener cuidado con los parámetros en el GROUP BY
            sql_grafica = f"""
                SELECT FORMAT(FechaHora, 'dd/MM') as FechaStr, SUM(Total) as Total 
                FROM Factura 
                WHERE FechaHora >= DATEADD(day, -7, GETDATE()) {filtro_user}
                GROUP BY FORMAT(FechaHora, 'dd/MM'), CAST(FechaHora AS DATE) 
                ORDER BY CAST(FechaHora AS DATE) ASC
            """
            cursor.execute(sql_grafica, params_base)
            historial = dictfetchall(cursor)
            
            chart_labels = [h['FechaStr'] for h in historial]
            chart_data = [float(h['Total']) for h in historial]

    except Exception as e:
        print(f"Error reportes: {e}")

    context = {
        'nombre_usuario': request.session.get('user_nombre'),
        'rol_usuario': rol,
        'reporte': data_reporte, # Aquí va toda la info (cant y total)
        'chart_labels': json.dumps(chart_labels),
        'chart_data': json.dumps(chart_data),
    }
    return render(request, 'tienda/reportes.html', context)

# ==========================================
#              PRODUCTOS
# ==========================================
@login_requerido
def productos_view(request):
    search_query = request.GET.get('q', '') 
    mostrar_desactivados = request.GET.get('mostrar_desactivados') 
    try:
        with connection.cursor() as cursor:
            where_clause = "WHERE (Nombre LIKE %s)"
            params = [f'%{search_query}%']
            if not mostrar_desactivados: where_clause += " AND Activo = 1"
            sql_query = f"SELECT Id_Producto, Nombre, PrecioVenta, Cantidad, StockMinimo, Activo FROM Productos {where_clause} ORDER BY Nombre"
            cursor.execute(sql_query, params)
            productos = dictfetchall(cursor)
    except Exception as e:
        productos = []
    context = {'nombre_usuario': request.session.get('user_nombre'), 'rol_usuario': request.session.get('user_rol'), 'productos': productos, 'search_query': search_query, 'mostrando_desactivados': bool(mostrar_desactivados)}
    return render(request, 'tienda/productos.html', context)

@admin_requerido
def productos_agregar_view(request):
    if request.method == 'POST':
        prod_id = request.POST.get('Id_Producto')
        # .strip() quita espacios al inicio y final para evitar "Coca Cola " vs "Coca Cola"
        prod_nombre = request.POST.get('Nombre').strip()
        prod_precio = request.POST.get('PrecioVenta')
        prod_cantidad = request.POST.get('Cantidad')
        prod_stock = request.POST.get('StockMinimo')
        ruta_db_para_foto = '' 
        
        if 'foto_del_producto' in request.FILES:
            try:
                archivo_foto = request.FILES['foto_del_producto']
                ruta_para_guardar = os.path.join(settings.BASE_DIR, 'Imagenes', archivo_foto.name)
                with open(ruta_para_guardar, 'wb+') as destination:
                    for chunk in archivo_foto.chunks():
                        destination.write(chunk)
                ruta_db_para_foto = f"/static/{archivo_foto.name}"
            except Exception as e:
                print(f"Error foto: {e}")
        
        try:
            with connection.cursor() as cursor:
                # 1. VALIDAR ID
                cursor.execute("SELECT COUNT(*) FROM Productos WHERE Id_Producto = %s", [prod_id])
                if cursor.fetchone()[0] > 0:
                    messages.error(request, f"¡El ID {prod_id} ya está ocupado!")
                    return redirect('productos_lista')

                # 2. VALIDAR NOMBRE (BLINDADO)
                # Usamos LOWER() para que "coca cola" sea igual a "COCA COLA" o "Coca Cola"
                cursor.execute("SELECT COUNT(*) FROM Productos WHERE LOWER(Nombre) = LOWER(%s)", [prod_nombre])
                if cursor.fetchone()[0] > 0:
                    messages.error(request, f"¡Ya existe un producto llamado '{prod_nombre}'! No podés duplicarlo.")
                    return redirect('productos_lista')

                # 3. GUARDAR
                cursor.execute("INSERT INTO Productos (Id_Producto, Nombre, PrecioVenta, Cantidad, StockMinimo, rutaFoto, Activo) VALUES (%s, %s, %s, %s, %s, %s, 1)", 
                               [prod_id, prod_nombre, prod_precio, prod_cantidad, prod_stock, ruta_db_para_foto])
            
            messages.success(request, f"¡Producto '{prod_nombre}' agregado con éxito!")
            return redirect('productos_lista')

        except Exception as e:
            print(f"Error al agregar producto: {e}")
            messages.error(request, "Ocurrió un error al guardar.")

    context = {'nombre_usuario': request.session.get('user_nombre'), 'rol_usuario': request.session.get('user_rol')}
    return render(request, 'tienda/productos_agregar.html', context)

@admin_requerido
def productos_eliminar_view(request, id_prod):
    try:
        with connection.cursor() as cursor:
            cursor.execute("UPDATE Productos SET Activo = 0 WHERE Id_Producto = %s", [id_prod])
            messages.success(request, "Producto desactivado.")
    except Exception as e:
        messages.error(request, f"Error: {e}")
    return redirect('productos_lista')

@admin_requerido
def productos_reactivar_view(request, id_prod):
    try:
        with connection.cursor() as cursor:
            cursor.execute("UPDATE Productos SET Activo = 1 WHERE Id_Producto = %s", [id_prod])
            messages.success(request, "Producto reactivado.")
    except Exception as e:
        messages.error(request, f"Error: {e}")
    return redirect('productos_lista')

@admin_requerido
def productos_editar_view(request, id_prod):
    # 1. Si le diste "Guardar Cambios" (POST)
    if request.method == 'POST':
        prod_nombre = request.POST.get('Nombre')
        prod_precio = request.POST.get('PrecioVenta')
        prod_cantidad = request.POST.get('Cantidad')
        prod_stock = request.POST.get('StockMinimo')
        ruta_db_para_foto = request.POST.get('rutaFotoActual') 
        
        # Procesar foto si subieron una nueva
        if 'foto_del_producto' in request.FILES:
            archivo_foto = request.FILES['foto_del_producto']
            ruta_para_guardar = os.path.join(settings.BASE_DIR, 'Imagenes', archivo_foto.name)
            try:
                with open(ruta_para_guardar, 'wb+') as destination:
                    for chunk in archivo_foto.chunks():
                        destination.write(chunk)
                ruta_db_para_foto = f"/static/{archivo_foto.name}"
            except: pass
            
        sql_query = "UPDATE Productos SET Nombre=%s, PrecioVenta=%s, Cantidad=%s, StockMinimo=%s, rutaFoto=%s WHERE Id_Producto=%s"
        params = [prod_nombre, prod_precio, prod_cantidad, prod_stock, ruta_db_para_foto, id_prod]
        
        try:
            with connection.cursor() as cursor:
                cursor.execute(sql_query, params)
            
            # --- ¡AQUÍ ESTÁ EL MENSAJE! ---
            messages.success(request, "Producto guardado correctamente.")
            
            return redirect('productos_lista') 
        except Exception as e:
            messages.error(request, f"Error al editar: {e}")
 
    # 2. Cargar datos para mostrar el formulario (GET)
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM Productos WHERE Id_Producto = %s", [id_prod])
            data = dictfetchall(cursor)
            if not data: return redirect('productos_lista')
            producto = data[0] 
    except Exception: return redirect('productos_lista')
    
    context = {
        'nombre_usuario': request.session.get('user_nombre'),
        'rol_usuario': request.session.get('user_rol'),
        'producto': producto
    }
    return render(request, 'tienda/productos_editar.html', context)
 
    # 2. Si solo estás entrando a ver el formulario (GET)
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM Productos WHERE Id_Producto = %s", [id_prod])
            data = dictfetchall(cursor)
            if not data: return redirect('productos_lista')
            producto = data[0] 
    except Exception: return redirect('productos_lista')
    
    context = {
        'nombre_usuario': request.session.get('user_nombre'),
        'rol_usuario': request.session.get('user_rol'),
        'producto': producto
    }
    return render(request, 'tienda/productos_editar.html', context)

# ==========================================
#              CLIENTES
# ==========================================
@login_requerido
def clientes_view(request):
    search_query = request.GET.get('q', '')
    mostrar_desactivados = request.GET.get('mostrar_desactivados') 
    try:
        with connection.cursor() as cursor:
            where_clause = "WHERE (C.Nombre LIKE %s OR C.Apellido LIKE %s)"
            params = [f'%{search_query}%', f'%{search_query}%']
            
            # 1. FILTRO DE ACTIVOS
            if not mostrar_desactivados:
                where_clause += " AND C.Activo = 1"
            
            # 2. ¡EL MACHETAZO! OCULTAR LOS OCASIONALES
            # Solo mostramos EsOcasional = 0 (Los frecuentes)
            where_clause += " AND C.EsOcasional = 0"

            sql_query = f"""
                SELECT
                    C.Id_Cliente, C.Nombre, C.Apellido, C.correo, C.Activo,
                    STRING_AGG(CT.numero_telefono_C, ', ') AS Telefonos
                FROM Clientes C
                LEFT JOIN ClienteTelefono CT ON C.Id_Cliente = CT.id_cliente
                {where_clause}
                GROUP BY C.Id_Cliente, C.Nombre, C.Apellido, C.correo, C.Activo
                ORDER BY C.Nombre
            """
            cursor.execute(sql_query, params)
            clientes = dictfetchall(cursor)
    except Exception as e:
        clientes = []
    context = {
        'nombre_usuario': request.session.get('user_nombre'), 
        'rol_usuario': request.session.get('user_rol'), 
        'clientes': clientes, 
        'search_query': search_query, 
        'mostrando_desactivados': bool(mostrar_desactivados)
    }
    return render(request, 'tienda/clientes.html', context)

@admin_requerido
def clientes_agregar_view(request):
    if request.method == 'POST':
        cli_id = request.POST.get('Id_Cliente')
        cli_nombre = request.POST.get('Nombre').strip()
        cli_apellido = request.POST.get('Apellido').strip()
        
        # --- VALIDACIÓN DE CORREO ---
        cli_correo = request.POST.get('Correo')
        if not cli_correo: 
            cli_correo = None
        else:
            cli_correo = cli_correo.strip().lower() # Convertir a minúsculas
            # Lista de dominios permitidos
            dominios_validos = ['@gmail.com', '@hotmail.com', '@yahoo.com', '@outlook.com', '@live.com', '@icloud.com', '@yahoo.es', '@hotmail.es', '@outlook.es']
            
            es_valido = False
            for dominio in dominios_validos:
                if cli_correo.endswith(dominio):
                    es_valido = True
                    break
            
            if not es_valido:
                messages.error(request, f"El correo '{cli_correo}' está mal escrito. Revisá la terminación (ej: @gmail.com).")
                return redirect('clientes_lista')
        # ----------------------------
        
        cli_tel_1 = request.POST.get('numero_telefono_C_1') 
        cli_tel_2 = request.POST.get('numero_telefono_C_2') 
        
        try:
            with transaction.atomic(): 
                with connection.cursor() as cursor:
                    # Validar ID
                    cursor.execute("SELECT COUNT(*) FROM Clientes WHERE Id_Cliente = %s", [cli_id])
                    if cursor.fetchone()[0] > 0:
                        messages.error(request, "El ID de Cliente ya existe.")
                        return redirect('clientes_lista')

                    # Validar Nombre Duplicado
                    cursor.execute("SELECT COUNT(*) FROM Clientes WHERE LOWER(Nombre) = LOWER(%s) AND LOWER(Apellido) = LOWER(%s)", [cli_nombre, cli_apellido])
                    if cursor.fetchone()[0] > 0:
                        messages.error(request, f"El cliente '{cli_nombre} {cli_apellido}' ya existe.")
                        return redirect('clientes_lista')

                    cursor.execute("INSERT INTO Clientes (Id_Cliente, Nombre, Apellido, Correo, Activo, EsOcasional) VALUES (%s, %s, %s, %s, 1, 0)", 
                                   [cli_id, cli_nombre, cli_apellido, cli_correo])
                    
                    cursor.execute("SELECT ISNULL(MAX(id_telefonoCli), 0) FROM ClienteTelefono")
                    next_id = cursor.fetchone()[0] + 1
                    
                    if cli_tel_1:
                        cursor.execute("INSERT INTO ClienteTelefono VALUES (%s, %s, %s)", [next_id, cli_id, cli_tel_1])
                        next_id += 1 
                    if cli_tel_2:
                        cursor.execute("INSERT INTO ClienteTelefono VALUES (%s, %s, %s)", [next_id, cli_id, cli_tel_2])
                
                messages.success(request, f"Cliente '{cli_nombre}' agregado correctamente.")
                return redirect('clientes_lista')
        except Exception as e:
            print(f"Error cliente: {e}")
            messages.error(request, "Error al guardar el cliente.")

    context = {'nombre_usuario': request.session.get('user_nombre'), 'rol_usuario': request.session.get('user_rol')}
    return render(request, 'tienda/clientes_agregar.html', context)

@admin_requerido
def clientes_eliminar_view(request, id_cli):
    try:
        with connection.cursor() as cursor:
            cursor.execute("UPDATE Clientes SET Activo = 0 WHERE Id_Cliente = %s", [id_cli])
            messages.success(request, "Cliente desactivado.")
    except Exception as e:
        messages.error(request, f"Error: {e}")
    return redirect('clientes_lista')

@admin_requerido
def clientes_reactivar_view(request, id_cli):
    try:
        with connection.cursor() as cursor:
            cursor.execute("UPDATE Clientes SET Activo = 1 WHERE Id_Cliente = %s", [id_cli])
            messages.success(request, "Cliente reactivado.")
    except Exception as e:
        messages.error(request, f"Error: {e}")
    return redirect('clientes_lista')

@admin_requerido
def clientes_editar_view(request, id_cli):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM Clientes WHERE Id_Cliente = %s", [id_cli])
            data = dictfetchall(cursor)
            if not data: return redirect('clientes_lista')
            cliente = data[0]
            cursor.execute("SELECT numero_telefono_C FROM ClienteTelefono WHERE id_cliente = %s", [id_cli])
            telefonos = dictfetchall(cursor)
    except: return redirect('clientes_lista')
    
    tel1 = telefonos[0]['numero_telefono_C'] if len(telefonos) > 0 else ''
    tel2 = telefonos[1]['numero_telefono_C'] if len(telefonos) > 1 else ''

    if request.method == 'POST':
        nom = request.POST.get('Nombre').strip()
        ape = request.POST.get('Apellido').strip()
        
        # --- VALIDACIÓN DE CORREO (OPCIONAL) ---
        cor = request.POST.get('Correo')
        
        # Si está vacío o solo tiene espacios, lo dejamos como None (NULL) y NO validamos
        if not cor or cor.strip() == "":
            cor = None
        else:
            # Si escribió algo, entonces SÍ validamos
            cor = cor.strip().lower()
            dominios_validos = ['@gmail.com', '@hotmail.com', '@yahoo.com', '@outlook.com', '@live.com', '@icloud.com', '@yahoo.es', '@hotmail.es', '@outlook.es']
            
            es_valido = False
            for dominio in dominios_validos:
                if cor.endswith(dominio):
                    es_valido = True
                    break
            
            if not es_valido:
                messages.error(request, f"El correo '{cor}' está mal escrito. Revisá la terminación.")
                return redirect('clientes_lista') # O render, según prefieras
        # ---------------------------------------
        
        t1 = request.POST.get('numero_telefono_C_1')
        t2 = request.POST.get('numero_telefono_C_2')
        
        try:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("UPDATE Clientes SET Nombre=%s, Apellido=%s, Correo=%s WHERE Id_Cliente=%s", [nom, ape, cor, id_cli])
                    
                    cursor.execute("DELETE FROM ClienteTelefono WHERE id_cliente = %s", [id_cli])
                    cursor.execute("SELECT ISNULL(MAX(id_telefonoCli), 0) FROM ClienteTelefono")
                    next_id = cursor.fetchone()[0] + 1
                    
                    if t1:
                        cursor.execute("INSERT INTO ClienteTelefono VALUES (%s, %s, %s)", [next_id, id_cli, t1])
                        next_id += 1
                    if t2:
                        cursor.execute("INSERT INTO ClienteTelefono VALUES (%s, %s, %s)", [next_id, id_cli, t2])
            
            messages.success(request, "Cliente actualizado correctamente.")
            return redirect('clientes_lista')
        except Exception as e:
            print(f"Error: {e}")
            messages.error(request, "Error al editar cliente.")
            
    context = {'cliente': cliente, 'telefono_1': tel1, 'telefono_2': tel2, 'nombre_usuario': request.session.get('user_nombre'), 'rol_usuario': request.session.get('user_rol')}
    return render(request, 'tienda/clientes_editar.html', context)
@login_requerido
def clientes_rapido_view(request):
    if request.method == 'POST':
        try:
            cid = request.POST.get('modal_cli_id')
            nom = request.POST.get('modal_cli_nombre')
            ape = request.POST.get('modal_cli_apellido')
            
            if not cid or not nom or not ape: 
                return JsonResponse({'error': "Faltan datos."}, status=400)

            with connection.cursor() as cursor:
                # Validar ID
                cursor.execute("SELECT count(*) FROM Clientes WHERE Id_Cliente = %s", [cid])
                if cursor.fetchone()[0] > 0: 
                    return JsonResponse({'error': "Ese ID ya existe."}, status=400)
                
                # ¡AQUÍ ESTÁ EL CAMBIO!
                # Guardamos con EsOcasional = 1
                sql = """
                    INSERT INTO Clientes (Id_Cliente, Nombre, Apellido, Correo, Activo, EsOcasional) 
                    VALUES (%s, %s, %s, 'N/A', 1, 1)
                """
                cursor.execute(sql, [cid, nom, ape])
            
            return JsonResponse({
                'mensaje': "Cliente rápido registrado.", 
                'cliente': {'id': cid, 'nombre_completo': f"{nom} {ape}"}
            })

        except Exception as e: 
            return JsonResponse({'error': str(e)}, status=500)
            
    return JsonResponse({'error': 'Error'}, status=400)

# ==========================================
#              PROVEEDORES
# ==========================================
@login_requerido
def proveedores_view(request):
    search_query = request.GET.get('q', '')
    mostrar_desactivados = request.GET.get('mostrar_desactivados') 
    try:
        with connection.cursor() as cursor:
            where_clause = "WHERE (P.nombre_proveedor LIKE %s)"
            params = [f'%{search_query}%']
            if not mostrar_desactivados:
                where_clause += " AND P.Activo = 1"
            sql_query = f"""
                SELECT
                    P.id_Proveedor, P.nombre_proveedor, P.correo, P.Direccion, P.Activo,
                    STRING_AGG(PT.numero_telefono_P, ', ') AS Telefonos
                FROM Proveedores P
                LEFT JOIN ProveedorTelefono PT ON P.id_Proveedor = PT.id_Proveedor
                {where_clause}
                GROUP BY P.id_Proveedor, P.nombre_proveedor, P.correo, P.Direccion, P.Activo
                ORDER BY P.nombre_proveedor
            """
            cursor.execute(sql_query, params)
            proveedores = dictfetchall(cursor)
    except Exception as e:
        proveedores = []
    context = {
        'nombre_usuario': request.session.get('user_nombre'),
        'rol_usuario': request.session.get('user_rol'),
        'proveedores': proveedores,
        'search_query': search_query,
        'mostrando_desactivados': bool(mostrar_desactivados)
    }
    return render(request, 'tienda/proveedores.html', context)
    
@admin_requerido
def proveedores_agregar_view(request):
    if request.method == 'POST':
        prov_id = request.POST.get('id_Proveedor')
        prov_nombre = request.POST.get('nombre_proveedor')
        prov_dir = request.POST.get('Direccion')
        prov_tel_1 = request.POST.get('numero_telefono_P_1')
        prov_tel_2 = request.POST.get('numero_telefono_P_2')
        
        # --- VALIDACIÓN DE CORREO ---
        prov_correo = request.POST.get('correo')
        if not prov_correo or prov_correo.strip() == "":
            prov_correo = None
        else:
            prov_correo = prov_correo.strip().lower()
            dominios_validos = ['@gmail.com', '@hotmail.com', '@yahoo.com', '@outlook.com', '@live.com', '@icloud.com', '@yahoo.es', '@hotmail.es', '@outlook.es']
            es_valido = False
            for dominio in dominios_validos:
                if prov_correo.endswith(dominio):
                    es_valido = True
                    break
            
            if not es_valido:
                messages.error(request, f"El correo '{prov_correo}' no es válido. Revisá la terminación.")
                return redirect('proveedores_lista')
        # ----------------------------

        try:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    # Validar ID
                    cursor.execute("SELECT COUNT(*) FROM Proveedores WHERE id_Proveedor = %s", [prov_id])
                    if cursor.fetchone()[0] > 0:
                        messages.error(request, "ID Proveedor repetido")
                        return redirect('proveedores_lista')
                    
                    # Validar Nombre
                    cursor.execute("SELECT COUNT(*) FROM Proveedores WHERE LOWER(nombre_proveedor) = LOWER(%s)", [prov_nombre.strip()])
                    if cursor.fetchone()[0] > 0:
                        messages.error(request, f"El proveedor '{prov_nombre}' ya existe.")
                        return redirect('proveedores_lista')

                    sql_prov = "INSERT INTO Proveedores (id_Proveedor, nombre_proveedor, correo, Direccion, Activo) VALUES (%s, %s, %s, %s, 1)"
                    cursor.execute(sql_prov, [prov_id, prov_nombre, prov_correo, prov_dir])
                    
                    cursor.execute("SELECT ISNULL(MAX(id_telefonoProve), 0) FROM ProveedorTelefono")
                    next_id_tel = cursor.fetchone()[0] + 1
                    
                    if prov_tel_1:
                        cursor.execute("INSERT INTO ProveedorTelefono VALUES (%s, %s, %s)", [next_id_tel, prov_id, prov_tel_1])
                        next_id_tel += 1 
                    if prov_tel_2:
                        cursor.execute("INSERT INTO ProveedorTelefono VALUES (%s, %s, %s)", [next_id_tel, prov_id, prov_tel_2])
            
            messages.success(request, f"Proveedor '{prov_nombre}' agregado.")
            return redirect('proveedores_lista')
        except Exception as e:
            print(f"Error: {e}")
            messages.error(request, "Error al guardar.")

    context = {'nombre_usuario': request.session.get('user_nombre'), 'rol_usuario': request.session.get('user_rol')}
    return render(request, 'tienda/proveedores_agregar.html', context)
    
@admin_requerido
def proveedores_eliminar_view(request, id_prov):
    try:
        with connection.cursor() as cursor:
            cursor.execute("UPDATE Proveedores SET Activo = 0 WHERE id_Proveedor = %s", [id_prov])
            messages.success(request, "Proveedor desactivado.")
    except Exception as e:
        messages.error(request, f"Error: {e}")
    return redirect('proveedores_lista')

@admin_requerido
def proveedores_reactivar_view(request, id_prov):
    try:
        with connection.cursor() as cursor:
            cursor.execute("UPDATE Proveedores SET Activo = 1 WHERE id_Proveedor = %s", [id_prov])
            messages.success(request, "Proveedor reactivado.")
    except Exception as e:
        messages.error(request, f"Error: {e}")
    return redirect('proveedores_lista')

@admin_requerido
def proveedores_editar_view(request, id_prov):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM Proveedores WHERE id_Proveedor = %s", [id_prov])
            data = dictfetchall(cursor)
            if not data: return redirect('proveedores_lista')
            proveedor = data[0]
            cursor.execute("SELECT numero_telefono_P FROM ProveedorTelefono WHERE id_Proveedor = %s", [id_prov])
            telefonos = dictfetchall(cursor)
    except: return redirect('proveedores_lista')
    t1 = telefonos[0]['numero_telefono_P'] if len(telefonos) > 0 else ''
    t2 = telefonos[1]['numero_telefono_P'] if len(telefonos) > 1 else ''

    if request.method == 'POST':
        nom = request.POST.get('nombre_proveedor')
        dir = request.POST.get('Direccion')
        tel1 = request.POST.get('numero_telefono_P_1')
        tel2 = request.POST.get('numero_telefono_P_2')
        
        # --- VALIDACIÓN DE CORREO ---
        cor = request.POST.get('correo')
        if not cor or cor.strip() == "":
            cor = None
        else:
            cor = cor.strip().lower()
            dominios_validos = ['@gmail.com', '@hotmail.com', '@yahoo.com', '@outlook.com', '@live.com', '@icloud.com', '@yahoo.es', '@hotmail.es', '@outlook.es']
            es_valido = False
            for dominio in dominios_validos:
                if cor.endswith(dominio):
                    es_valido = True
                    break
            if not es_valido:
                messages.error(request, f"El correo '{cor}' no es válido.")
                return redirect('proveedores_lista')
        # ----------------------------

        try:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("UPDATE Proveedores SET nombre_proveedor=%s, correo=%s, Direccion=%s WHERE id_Proveedor=%s", [nom, cor, dir, id_prov])
                    cursor.execute("DELETE FROM ProveedorTelefono WHERE id_Proveedor = %s", [id_prov])
                    cursor.execute("SELECT ISNULL(MAX(id_telefonoProve), 0) FROM ProveedorTelefono")
                    next_id = cursor.fetchone()[0] + 1
                    if tel1:
                        cursor.execute("INSERT INTO ProveedorTelefono VALUES (%s, %s, %s)", [next_id, id_prov, tel1])
                        next_id += 1
                    if tel2:
                        cursor.execute("INSERT INTO ProveedorTelefono VALUES (%s, %s, %s)", [next_id, id_prov, tel2])
            messages.success(request, "Proveedor actualizado.")
            return redirect('proveedores_lista')
        except Exception as e: print(f"Error: {e}")

    context = {
        'proveedor': proveedor, 
        'telefono_1': t1, 
        'telefono_2': t2,
        'nombre_usuario': request.session.get('user_nombre'),
        'rol_usuario': request.session.get('user_rol'),
    }
    return render(request, 'tienda/proveedores_editar.html', context)
# ==========================================
#    ASIGNAR PROVEEDORES (COSTOS)
# ==========================================

@admin_requerido
def proveedor_producto_lista_view(request):
    search_query = request.GET.get('q', '')
    mostrar_desactivados = request.GET.get('mostrar_desactivados')
    orden = request.GET.get('orden', 'nombre') # Por defecto ordena por nombre
    
    try:
        with connection.cursor() as cursor:
            where_clause = "WHERE (Prov.nombre_proveedor LIKE %s OR Prod.Nombre LIKE %s)"
            params = [f'%{search_query}%', f'%{search_query}%']
            
            if not mostrar_desactivados:
                where_clause += " AND PP.Activo = 1"

            # --- LÓGICA DE ORDENAMIENTO ---
            if orden == 'precio_menor':
                order_sql = "ORDER BY PP.PrecioCompra ASC" # Barato primero
            elif orden == 'precio_mayor':
                order_sql = "ORDER BY PP.PrecioCompra DESC" # Caro primero
            else:
                order_sql = "ORDER BY Prod.Nombre ASC" # Por defecto (A-Z)

            sql = f"""
                SELECT 
                    PP.Id_Proveedor, 
                    PP.Id_Producto, 
                    PP.PrecioCompra,
                    PP.CantidadCompra,
                    PP.Activo,
                    Prov.nombre_proveedor AS NombreProveedor,
                    Prod.Nombre AS NombreProducto
                FROM ProveedorProducto PP
                JOIN Proveedores Prov ON PP.Id_Proveedor = Prov.id_Proveedor
                JOIN Productos Prod ON PP.Id_Producto = Prod.Id_Producto
                {where_clause}
                {order_sql}
            """
            cursor.execute(sql, params)
            asignaciones = dictfetchall(cursor)
    except Exception as e:
        asignaciones = []
        print(f"Error listando: {e}")

    return render(request, 'tienda/proveedor_producto_lista.html', {
        'asignaciones': asignaciones,
        'search_query': search_query,
        'mostrando_desactivados': bool(mostrar_desactivados),
        'orden_actual': orden, # Para que el select se quede marcado
        'nombre_usuario': request.session.get('user_nombre'),
        'rol_usuario': request.session.get('user_rol'),
    })

@admin_requerido
def proveedor_producto_agregar_view(request):
    productos, proveedores = [], []
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT Id_Producto, Nombre FROM Productos WHERE Activo = 1 ORDER BY Nombre")
            productos = dictfetchall(cursor)
            cursor.execute("SELECT id_Proveedor, nombre_proveedor FROM Proveedores WHERE Activo = 1 ORDER BY nombre_proveedor")
            proveedores = dictfetchall(cursor)
    except: pass

    if request.method == 'POST':
        id_prod = request.POST.get('id_producto')
        id_prov = request.POST.get('id_proveedor')
        precio = request.POST.get('precio_compra')
        cantidad = request.POST.get('cantidad_compra')

        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM ProveedorProducto WHERE Id_Producto = %s AND Id_Proveedor = %s", [id_prod, id_prov])
                if cursor.fetchone()[0] > 0:
                    sql = "UPDATE ProveedorProducto SET PrecioCompra=%s, CantidadCompra=%s, Activo=1 WHERE Id_Producto=%s AND Id_Proveedor=%s"
                    cursor.execute(sql, [precio, cantidad, id_prod, id_prov])
                else:
                    sql = "INSERT INTO ProveedorProducto (Id_Producto, Id_Proveedor, PrecioCompra, CantidadCompra, Activo) VALUES (%s, %s, %s, %s, 1)"
                    cursor.execute(sql, [id_prod, id_prov, precio, cantidad])
            
            messages.success(request, "Costo asignado correctamente.")
            return redirect('proveedor_producto_lista')
        except Exception as e:
            print(f"Error al asignar: {e}")

    context = {
        'productos': productos,
        'proveedores': proveedores,
        'nombre_usuario': request.session.get('user_nombre'),
        'rol_usuario': request.session.get('user_rol'),
    }
    return render(request, 'tienda/proveedor_producto_agregar.html', context)

@admin_requerido
def proveedor_producto_editar_view(request, id_prov, id_prod):
    asignacion = None
    try:
        with connection.cursor() as cursor:
            sql = """
                SELECT PP.*, P.Nombre as NombreProducto, Pr.nombre_proveedor as NombreProveedor 
                FROM ProveedorProducto PP
                JOIN Productos P ON PP.Id_Producto = P.Id_Producto
                JOIN Proveedores Pr ON PP.Id_Proveedor = Pr.id_Proveedor
                WHERE PP.Id_Proveedor = %s AND PP.Id_Producto = %s
            """
            cursor.execute(sql, [id_prov, id_prod])
            data = dictfetchall(cursor)
            if data: asignacion = data[0]
    except: pass

    if not asignacion: return redirect('proveedor_producto_lista')

    if request.method == 'POST':
        precio = request.POST.get('precio_compra')
        cantidad = request.POST.get('cantidad_compra')
        try:
            with connection.cursor() as cursor:
                sql = "UPDATE ProveedorProducto SET PrecioCompra=%s, CantidadCompra=%s WHERE Id_Proveedor=%s AND Id_Producto=%s"
                cursor.execute(sql, [precio, cantidad, id_prov, id_prod])
            messages.success(request, "Costo actualizado.")
            return redirect('proveedor_producto_lista')
        except Exception as e: print(f"Error editar: {e}")

    return render(request, 'tienda/proveedor_producto_editar.html', {
        'asignacion': asignacion,
        'nombre_usuario': request.session.get('user_nombre'), 
        'rol_usuario': request.session.get('user_rol')
    })

@admin_requerido
def proveedor_producto_eliminar_view(request, id_prov, id_prod):
    try:
        with connection.cursor() as cursor:
            sql = "UPDATE ProveedorProducto SET Activo = 0 WHERE Id_Proveedor = %s AND Id_Producto = %s"
            cursor.execute(sql, [id_prov, id_prod])
            messages.success(request, "Costo desactivado.")
    except: pass
    return redirect('proveedor_producto_lista')

@admin_requerido
def proveedor_producto_reactivar_view(request, id_prov, id_prod):
    try:
        with connection.cursor() as cursor:
            sql = "UPDATE ProveedorProducto SET Activo = 1 WHERE Id_Proveedor = %s AND Id_Producto = %s"
            cursor.execute(sql, [id_prov, id_prod])
            messages.success(request, "Costo reactivado.")
    except: pass
    return redirect('proveedor_producto_lista')

#este sirve para avastecer en la obcion de costos
@admin_requerido
def registrar_compra_view(request):
    if request.method == 'POST':
        id_prov = request.POST.get('id_proveedor')
        id_prod = request.POST.get('id_producto')
        cant_bultos = int(request.POST.get('cantidad_bultos')) # Cuántas cajas compró

        if cant_bultos <= 0:
            messages.error(request, "La cantidad debe ser mayor a 0.")
            return redirect('proveedor_producto_lista')

        try:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    # 1. Averiguar cuántas unidades trae el paquete de este proveedor
                    cursor.execute("SELECT CantidadCompra, PrecioCompra FROM ProveedorProducto WHERE Id_Proveedor = %s AND Id_Producto = %s", [id_prov, id_prod])
                    data = cursor.fetchone()
                    
                    if not data:
                        messages.error(request, "No se encontró la configuración de costo.")
                        return redirect('proveedor_producto_lista')

                    unidades_por_bulto = data[0]
                    # precio_costo = data[1] (Podríamos usarlo para registrar gasto, pero por ahora solo stock)

                    # 2. Calcular total de unidades a sumar (Ej: 2 cajas * 12 unids = 24)
                    total_a_sumar = cant_bultos * unidades_por_bulto

                    # 3. Actualizar Inventario del Producto
                    cursor.execute("UPDATE Productos SET Cantidad = Cantidad + %s WHERE Id_Producto = %s", [total_a_sumar, id_prod])
                    
                    # 4. (Opcional) Podrías guardar esto en una tabla 'Compras' para historial, 
                    # pero por ahora solo actualizamos stock.

            messages.success(request, f"¡Inventario actualizado! Se agregaron {total_a_sumar} unidades.")
            
        except Exception as e:
            print(f"Error abasteciendo: {e}")
            messages.error(request, "Error al actualizar stock.")

    return redirect('proveedor_producto_lista')
# ==========================================
#              FACTURACIÓN
# ==========================================
@login_requerido
def facturacion_view(request):
    if 'carrito' not in request.session: request.session['carrito'] = []

    search_query = request.GET.get('q_producto', '') 
    search_cliente_query = request.GET.get('q_cliente', '')
    cliente_seleccionado = request.GET.get('cliente_seleccionado', '')
    monto_pagado_previo = request.GET.get('monto_pagado', '')

    clientes_buscados = [] 
    try:
        with connection.cursor() as cursor:
            # CASO A: Si estás buscando por nombre en la barrita
            if search_cliente_query:
                sql = "SELECT Id_Cliente, Nombre, Apellido FROM Clientes WHERE (Nombre LIKE %s OR Apellido LIKE %s OR CAST(Id_Cliente AS VARCHAR) LIKE %s) AND Activo = 1"
                cursor.execute(sql, [f'%{search_cliente_query}%', f'%{search_cliente_query}%', f'%{search_cliente_query}%'])
                clientes_buscados = dictfetchall(cursor)
            
            # CASO B (EL ARREGLO): Si no buscaste nada, pero ya tenías uno seleccionado (ej: después de un error)
            elif cliente_seleccionado:
                sql = "SELECT Id_Cliente, Nombre, Apellido FROM Clientes WHERE Id_Cliente = %s"
                cursor.execute(sql, [cliente_seleccionado])
                clientes_buscados = dictfetchall(cursor)

    except Exception as e:
        messages.error(request, f"Error al cargar clientes: {e}")

    productos_en_pantalla = [] 
    if search_query:
        try:
            with connection.cursor() as cursor:
                sql = "SELECT Id_Producto, Nombre, PrecioVenta, Cantidad, rutaFoto FROM Productos WHERE Nombre LIKE %s AND Cantidad > 0 AND Activo = 1 ORDER BY Nombre ASC"
                cursor.execute(sql, [f'%{search_query}%'])
                productos_en_pantalla = dictfetchall(cursor)
        except Exception as e:
            messages.error(request, f"Error al buscar productos: {e}")
    else:
        try:
            with connection.cursor() as cursor:
                sql = "SELECT Id_Producto, Nombre, PrecioVenta, Cantidad, rutaFoto FROM Productos WHERE Cantidad > 0 AND Activo = 1 ORDER BY Nombre ASC"
                cursor.execute(sql)
                productos_en_pantalla = dictfetchall(cursor)
        except Exception as e:
            messages.error(request, f"Error al cargar productos: {e}")
            
    carrito = request.session['carrito']
    total_factura = sum(Decimal(item['subtotal']) for item in carrito)

    context = {
        'nombre_usuario': request.session.get('user_nombre'), 'rol_usuario': request.session.get('user_rol'),
        'clientes_buscados': clientes_buscados, 
        'productos_en_pantalla': productos_en_pantalla,
        'search_query': search_query, 
        'search_cliente_query': search_cliente_query,
        'cliente_seleccionado': cliente_seleccionado,
        'monto_pagado_previo': monto_pagado_previo,
        'carrito': carrito,
        'total_factura': total_factura,
    }
    return render(request, 'tienda/facturacion.html', context)

@login_requerido
def facturacion_agregar_item(request):
    if request.method == 'POST':
        try:
            prod_id = request.POST.get('producto_id')
            cantidad_a_agregar = int(request.POST.get('cantidad'))
            
            if cantidad_a_agregar <= 0: 
                return JsonResponse({'error': "La cantidad debe ser mayor a 0."}, status=400)

            # 1. Buscar datos reales del producto en la BD
            with connection.cursor() as cursor:
                cursor.execute("SELECT Nombre, PrecioVenta, Cantidad FROM Productos WHERE Id_Producto = %s AND Activo = 1", [prod_id])
                data = dictfetchall(cursor)
            
            if not data: return JsonResponse({'error': "No existe"}, status=404)
            prod_db = data[0]
            stock_real = prod_db['Cantidad']
            precio_unitario = Decimal(prod_db['PrecioVenta'])
            
            # 2. Obtener el carrito actual
            if 'carrito' not in request.session: request.session['carrito'] = []
            carrito = request.session['carrito']
            
            # --- LÓGICA PARA NO REPETIR ---
            producto_encontrado = False
            
            for item in carrito:
                # Si el ID coincide (lo convertimos a str para asegurar)
                if str(item['id_producto']) == str(prod_id):
                    
                    # Calculamos la nueva cantidad total
                    nueva_cantidad = int(item['cantidad']) + cantidad_a_agregar
                    
                    # Validamos Stock acumulado
                    if nueva_cantidad > stock_real:
                        return JsonResponse({'error': f"¡Stock insuficiente! Ya tenés {item['cantidad']} en carrito y solo hay {stock_real} en total."}, status=400)
                    
                    # Actualizamos el item existente
                    item['cantidad'] = nueva_cantidad
                    item['subtotal'] = f"{precio_unitario * nueva_cantidad:.2f}"
                    producto_encontrado = True
                    break # Ya lo encontramos, dejamos de buscar
            
            # Si NO estaba en el carrito, lo agregamos como nuevo
            if not producto_encontrado:
                if cantidad_a_agregar > stock_real:
                    return JsonResponse({'error': f"Solo hay {stock_real} en stock."}, status=400)
                
                nuevo_item = {
                    'id_producto': prod_id, 
                    'nombre': prod_db['Nombre'], 
                    'cantidad': cantidad_a_agregar, 
                    'precio_unitario': f"{precio_unitario:.2f}", 
                    'subtotal': f"{precio_unitario * cantidad_a_agregar:.2f}"
                }
                carrito.append(nuevo_item)
            
            # 3. Guardar y Recalcular Total
            request.session['carrito'] = carrito
            request.session.modified = True 
            
            total_factura = sum(Decimal(i['subtotal']) for i in carrito)
            
            return JsonResponse({
                'mensaje': f"Producto actualizado: {prod_db['Nombre']}", 
                'carrito': carrito, 
                'total_factura': f"{total_factura:.2f}"
            })

        except Exception as e: return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Bad request'}, status=400)

# --- AUTOCOMPRA (SOY YO) ---
@login_requerido
def autocompra_view(request):
    if request.method == 'POST':
        nombre_usuario = request.session.get('user_nombre', 'Usuario')
        apellido_fijo = "(Personal)" # Para diferenciarlo de un cliente normal

        try:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    # 1. Buscar si ya existe el "Cliente Usuario"
                    cursor.execute("SELECT Id_Cliente, Nombre, Apellido FROM Clientes WHERE Nombre = %s AND Apellido = %s", [nombre_usuario, apellido_fijo])
                    data = dictfetchall(cursor)

                    if data:
                        # Ya existe, lo devolvemos
                        cliente = data[0]
                        return JsonResponse({
                            'mensaje': f"Cliente asignado: {cliente['Nombre']}",
                            'cliente': {'id': cliente['Id_Cliente'], 'nombre_completo': f"{cliente['Nombre']} {cliente['Apellido']}"}
                        })
                    else:
                        # 2. No existe, lo creamos
                        # Generar ID nuevo (Busca el hueco o el máximo)
                        cursor.execute("SELECT ISNULL(MAX(Id_Cliente), 0) + 1 FROM Clientes")
                        new_id = cursor.fetchone()[0]
                        
                        # Validamos que ese ID no exista (por si las moscas)
                        cursor.execute("SELECT COUNT(*) FROM Clientes WHERE Id_Cliente = %s", [new_id])
                        while cursor.fetchone()[0] > 0:
                            new_id += 1 # Buscamos el siguiente libre
                        
                        # Insertar como Cliente Frecuente (EsOcasional=0) para que salga en reportes
                        sql = "INSERT INTO Clientes (Id_Cliente, Nombre, Apellido, Correo, Activo, EsOcasional) VALUES (%s, %s, %s, 'N/A', 1, 0)"
                        cursor.execute(sql, [new_id, nombre_usuario, apellido_fijo])
                        
                        return JsonResponse({
                            'mensaje': "Perfil de autocompra creado y asignado.",
                            'cliente': {'id': new_id, 'nombre_completo': f"{nombre_usuario} {apellido_fijo}"}
                        })

        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
            
    return JsonResponse({'error': 'Método no permitido'}, status=400)

@login_requerido
def facturacion_eliminar_item(request, item_index):
    try:
        carrito = request.session.get('carrito', [])
        if 0 <= item_index < len(carrito):
            del carrito[item_index]
            request.session.modified = True
            
            total = sum(Decimal(i['subtotal']) for i in carrito)
            
            
            return JsonResponse({
                'mensaje': "Eliminado", 
                'carrito': carrito, 
                'total_factura': f"{total:.2f}" 
            })
    except: pass
    return JsonResponse({'error': "Error"}, status=500)

@login_requerido
def facturacion_guardar_view(request):
    if request.method == 'POST':
        id_cliente = request.POST.get('cliente_id')
        monto_pagado_str = request.POST.get('monto_pagado') 
        id_usuario = request.session.get('user_id')
        carrito = request.session.get('carrito', [])
        
        # Validaciones iniciales
        if not id_cliente:
            messages.error(request, "Tenés que seleccionar un cliente.")
            return redirect('facturacion_view')
        
        if not carrito:
            messages.error(request, "El carrito está vacío.")
            # Aquí devolvemos el cliente seleccionado por si acaso
            return redirect(f'/facturacion/?cliente_seleccionado={id_cliente}')
            
        if not monto_pagado_str:
            messages.error(request, "Falta el monto de pago.")
            return redirect(f'/facturacion/?cliente_seleccionado={id_cliente}')

        try:
            total_factura = sum(Decimal(item['subtotal']) for item in carrito)
            monto_pagado = Decimal(monto_pagado_str)
            
            # 1. VALIDACIÓN DE DINERO (Aquí es donde fallaba)
            if monto_pagado < total_factura:
                messages.error(request, f"Pago insuficiente. Faltan C$ {total_factura - monto_pagado}")
                # ¡EL ARREGLO!: Redirigimos enviando el ID del cliente y el monto para que no se borren
                return redirect(f'/facturacion/?cliente_seleccionado={id_cliente}&monto_pagado={monto_pagado_str}')

            cambio = monto_pagado - total_factura

            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("SELECT ISNULL(MAX(id_factura), 0) + 1 FROM Factura")
                    new_id = cursor.fetchone()[0]
                    
                    # Insertar Factura
                    cursor.execute("INSERT INTO Factura (id_factura, id_cliente, Id_Usuario, FechaHora, Total, MontoPagado, Cambio) VALUES (%s, %s, %s, GETDATE(), %s, %s, %s)", 
                                   [new_id, id_cliente, id_usuario, total_factura, monto_pagado, cambio])
                    
                    cursor.execute("SELECT ISNULL(MAX(Id_Detalle), 0) FROM DetalleFactura")
                    next_det = cursor.fetchone()[0] + 1
                    
                    for item in carrito:
                        cursor.execute("INSERT INTO DetalleFactura (Id_Detalle, Id_Factura, Id_Producto, cantidad, Subtotal) VALUES (%s, %s, %s, %s, %s)",
                                       [next_det, new_id, item['id_producto'], item['cantidad'], Decimal(item['subtotal'])])
                        next_det += 1
                        cursor.execute("UPDATE Productos SET Cantidad = Cantidad - %s WHERE Id_Producto = %s", [item['cantidad'], item['id_producto']])

            request.session['carrito'] = [] 
            messages.success(request, f"Factura #{new_id} guardada.")
            return redirect('factura_recibo', id_fact=new_id)
            
        except Exception as e:
            print(f"Error Factura: {e}")
            messages.error(request, f"Error al guardar: {e}")
            # Si falla SQL, también devolvemos al cliente para no perderlo
            return redirect(f'/facturacion/?cliente_seleccionado={id_cliente}&monto_pagado={monto_pagado_str}')
            
    return redirect('facturacion_view')

@login_requerido
def factura_recibo_view(request, id_fact):
    factura = None
    detalles = []
    try:
        with connection.cursor() as cursor:
            # 1. Datos de la Factura (Con MontoPagado y Cambio)
            sql_fact = """
                SELECT 
                    F.id_factura, F.FechaHora, F.Total, F.MontoPagado, F.Cambio,
                    C.Nombre AS ClienteNombre, C.Apellido AS ClienteApellido,
                    U.Nombre AS CajeroNombre
                FROM Factura F
                JOIN Clientes C ON F.id_cliente = C.Id_Cliente
                JOIN Usuarios U ON F.Id_Usuario = U.IdUsuario
                WHERE F.id_factura = %s
            """
            cursor.execute(sql_fact, [id_fact])
            data = dictfetchall(cursor)
            
            if not data:
                return redirect('facturacion_view')
            factura = data[0]

            # 2. Detalles (Calculando Precio Unitario al vuelo)
            sql_det = """
                SELECT 
                    D.cantidad, D.Subtotal,
                    P.Nombre as ProductoNombre,
                    (D.Subtotal / NULLIF(D.cantidad, 0)) as PrecioUnitario
                FROM DetalleFactura D
                JOIN Productos P ON D.Id_Producto = P.Id_Producto
                WHERE D.Id_Factura = %s
            """
            cursor.execute(sql_det, [id_fact])
            detalles = dictfetchall(cursor)
            
    except Exception as e:
        print(f"💥 Error Recibo: {e}")
        messages.error(request, "Error al generar el recibo.")
        return redirect('facturacion_view')

    return render(request, 'tienda/factura_recibo.html', {'factura': factura, 'detalles': detalles})

@login_requerido
def prediccion_view(request):
    context = {'nombre_usuario': request.session.get('user_nombre'), 'rol_usuario': request.session.get('user_rol'), 'resultados': None}
    if request.method == 'POST':
        try:
            costo = Decimal(request.POST.get('costo_total_lote') or 0)
            cant = int(request.POST.get('cantidad_comprada') or 0)
            precio = Decimal(request.POST.get('precio_venta_unitario') or 0)
            if costo <= 0 or cant <= 0 or precio <= 0: messages.error(request, "Datos inválidos.")
            else:
                c_unit = costo / cant
                g_unit = precio - c_unit
                context['resultados'] = {'costo_unitario': c_unit, 'ganancia_unitaria': g_unit, 'ganancia_total_lote': g_unit * cant}
                messages.success(request, "Calculado.")
        except: messages.error(request, "Error en datos.")
    return render(request, 'tienda/prediccion.html', context)