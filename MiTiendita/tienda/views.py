# tienda/views.py
from django.db.models import Max
from django.db.models import Q
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.hashers import make_password
from django.core.files.storage import FileSystemStorage
from .models import Productos, Clientes, Proveedores, ProveedorProducto, Facturas, DetalleFactura
import uuid 
from django.core.mail import send_mail 
from django.urls import reverse
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
    # 1. Ventas de Hoy (Usando nombres reales de tu tabla Factura)
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT ISNULL(SUM(Total), 0) 
            FROM Factura 
            WHERE CAST(FechaHora AS DATE) = CAST(GETDATE() AS DATE)
        """)
        venta_hoy = cursor.fetchone()[0]

    # 2. Ventas del Mes
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT ISNULL(SUM(Total), 0) 
            FROM Factura 
            WHERE MONTH(FechaHora) = MONTH(GETDATE()) 
            AND YEAR(FechaHora) = YEAR(GETDATE())
        """)
        venta_mes = cursor.fetchone()[0]

    # 3. Productos con Stock Bajo (Usando nombres reales de tu tabla Productos)
    lista_bajos_stock = []
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT Id_Producto, Nombre, Cantidad 
            FROM Productos 
            WHERE Cantidad <= StockMinimo AND Activo = 1
        """)
        rows = cursor.fetchall()
        for row in rows:
            lista_bajos_stock.append({
                'Id_Producto': row[0],
                'Nombre': row[1],
                'Cantidad': row[2]
            })

    bajos_stock = len(lista_bajos_stock)

    # --- DATOS PARA GRÁFICOS (Ahora con datos reales de venta_hoy) ---
    labels_dias = ["23/12"] 
    data_dias = [float(venta_hoy)]
    
    # Podés dejar estos fijos por ahora o traerlos con otro SELECT
    labels_prod = ["Ajo", "Achiote", "Ositos", "Zambo Chicharrón", "Ranchitas de chiles"]
    data_prod = [4, 4, 4, 4, 3]

    context = {
        'venta_hoy': venta_hoy,
        'venta_mes': venta_mes,
        'bajos_stock': bajos_stock,
        'lista_bajos_stock': lista_bajos_stock,
        'labels_dias_json': json.dumps(labels_dias),
        'data_dias_json': json.dumps(data_dias),
        'labels_prod_json': json.dumps(labels_prod),
        'data_prod_json': json.dumps(data_prod),
        'nombre_usuario': request.session.get('user_nombre'),
        'rol_usuario': request.session.get('user_rol'),
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
            where_clause = "WHERE (P.Nombre LIKE %s)"
            params = [f'%{search_query}%']
            if not mostrar_desactivados: where_clause += " AND P.Activo = 1"
            
            # Consulta con JOIN para traer Proveedor y Costo
            sql_query = f"""
                SELECT 
                    P.Id_Producto, P.Nombre, P.PrecioVenta, P.Cantidad, P.StockMinimo, P.Activo,
                    Prov.nombre_proveedor AS ProveedorNombre,
                    PP.PrecioCompra AS PrecioCosto
                FROM Productos P
                LEFT JOIN Proveedores Prov ON P.IdProveedor = Prov.id_Proveedor
                LEFT JOIN ProveedorProducto PP ON P.Id_Producto = PP.Id_Producto AND P.IdProveedor = PP.Id_Proveedor
                {where_clause} 
                ORDER BY P.Nombre
            """
            cursor.execute(sql_query, params)
            productos = dictfetchall(cursor)
    except Exception as e:
        productos = []
    context = {'nombre_usuario': request.session.get('user_nombre'), 'rol_usuario': request.session.get('user_rol'), 'productos': productos, 'search_query': search_query, 'mostrando_desactivados': bool(mostrar_desactivados)}
    return render(request, 'tienda/productos.html', context)


from django.core.files.storage import FileSystemStorage
from django.db import connection, transaction
# Asegúrate de tener los imports necesarios arriba

def productos_agregar_view(request):
    if request.method == 'POST':
        # 1. Datos del Producto (Venta)
        nombre = request.POST.get('nombre')
        precio_venta = request.POST.get('precio_venta')
        stock_inicial = request.POST.get('cantidad')
        stock_min = request.POST.get('stock_min')
        
        # 2. Datos del Proveedor (Compra)
        id_prov = request.POST.get('id_proveedor')
        unidades_por_paquete = request.POST.get('cantidad_compra') 
        precio_costo = request.POST.get('precio_compra')

        # 3. Manejar la Foto
        ruta_foto = None
        if 'foto' in request.FILES:
            imagen = request.FILES['foto']
            fs = FileSystemStorage()
            filename = fs.save(imagen.name, imagen)
            ruta_foto = fs.url(filename)

        try:
            with transaction.atomic():
                # A. Generar ID Manualmente (Como lo tenías)
                nuevo_id = 1
                with connection.cursor() as cursor:
                    cursor.execute("SELECT ISNULL(MAX(Id_Producto), 0) + 1 FROM Productos")
                    row = cursor.fetchone()
                    if row:
                        nuevo_id = row[0]

                # B. Crear el Producto
                nuevo_producto = Productos(
                    id_producto=nuevo_id,
                    nombre=nombre,
                    precioventa=precio_venta,
                    cantidad=stock_inicial,
                    stockminimo=stock_min,
                    
                    # Usamos el nombre exacto del campo definido en el modelo
                    idproveedor_id=id_prov, 
                    
                    rutafoto=ruta_foto,
                    activo=True
                )
                # IMPORTANTE: Al ser managed=False y manual, le decimos que es una inserción nueva
                nuevo_producto.save(force_insert=True)

                # C. Guardar el Costo de Compra inicial (si aplica)
                if id_prov and precio_costo:
                    with connection.cursor() as cursor:
                        sql_costo = """
                            INSERT INTO ProveedorProducto (Id_Producto, Id_Proveedor, PrecioCompra, CantidadCompra, Activo)
                            VALUES (%s, %s, %s, %s, 1)
                        """
                        cursor.execute(sql_costo, [nuevo_id, id_prov, precio_costo, unidades_por_paquete])

            messages.success(request, f"¡Producto '{nombre}' creado con éxito! (ID Asignado: {nuevo_id})")
            return redirect('productos_lista') # O la URL que uses para listar
            
        except Exception as e:
            messages.error(request, f"Error al guardar el producto: {e}")

    # --- PARTE GET (Cargar proveedores para el formulario) ---
    proveedores = []
    try:
        # Usamos el ORM si es posible, o tu query raw si prefieres
        # Opción Raw (como lo tenías):
        with connection.cursor() as cursor:
            cursor.execute("SELECT id_Proveedor, nombre_proveedor FROM Proveedores WHERE Activo = 1")
            # Convertimos a lista de diccionarios manualmente para el template
            columns = [col[0] for col in cursor.description]
            proveedores = [
                dict(zip(columns, row))
                for row in cursor.fetchall()
            ]
    except Exception as e:
        print(f"Error cargando proveedores: {e}")

    return render(request, 'tienda/productos_agregar.html', {'proveedores': proveedores})

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
    # 1. Si se enviaron los cambios (POST)
    if request.method == 'POST':
        nombre = request.POST.get('Nombre')
        precio_venta = request.POST.get('PrecioVenta')
        cantidad = request.POST.get('Cantidad')
        stock_min = request.POST.get('StockMinimo')
        id_prov = request.POST.get('id_proveedor')
        precio_costo = request.POST.get('precio_compra')
        unidades_paquete = request.POST.get('cantidad_compra')
        ruta_foto_actual = request.POST.get('rutaFotoActual')

        # Procesar nueva foto con FileSystemStorage (Carpeta Media)
        if 'foto_del_producto' in request.FILES:
            archivo = request.FILES['foto_del_producto']
            fs = FileSystemStorage()
            filename = fs.save(archivo.name, archivo)
            ruta_foto_actual = fs.url(filename)

        try:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    # A. Actualizar tabla Productos
                    sql_prod = """
                        UPDATE Productos 
                        SET Nombre=%s, PrecioVenta=%s, Cantidad=%s, StockMinimo=%s, rutaFoto=%s, IdProveedor=%s 
                        WHERE Id_Producto=%s
                    """
                    cursor.execute(sql_prod, [nombre, precio_venta, cantidad, stock_min, ruta_foto_actual, id_prov, id_prod])

                    # B. Actualizar o Insertar en ProveedorProducto (Costo y Empaque)
                    if id_prov and precio_costo:
                        cursor.execute("SELECT COUNT(*) FROM ProveedorProducto WHERE Id_Producto=%s AND Id_Proveedor=%s", [id_prod, id_prov])
                        if cursor.fetchone()[0] > 0:
                            cursor.execute("UPDATE ProveedorProducto SET PrecioCompra=%s, CantidadCompra=%s WHERE Id_Producto=%s AND Id_Proveedor=%s", 
                                           [precio_costo, unidades_paquete, id_prod, id_prov])
                        else:
                            cursor.execute("INSERT INTO ProveedorProducto (Id_Producto, Id_Proveedor, PrecioCompra, CantidadCompra, Activo) VALUES (%s, %s, %s, %s, 1)", 
                                           [id_prod, id_prov, precio_costo, unidades_paquete])

            messages.success(request, "Producto y datos de proveedor actualizados correctamente.")
            return redirect('productos_lista')
        except Exception as e:
            messages.error(request, f"Error al editar: {e}")

    # 2. Cargar datos para el formulario (GET)
    try:
        with connection.cursor() as cursor:
            # Traer producto unido con su costo actual
            sql = """
                SELECT P.*, PP.PrecioCompra, PP.CantidadCompra 
                FROM Productos P 
                LEFT JOIN ProveedorProducto PP ON P.Id_Producto = PP.Id_Producto AND P.IdProveedor = PP.Id_Proveedor
                WHERE P.Id_Producto = %s
            """
            cursor.execute(sql, [id_prod])
            producto = dictfetchall(cursor)[0]
            
            # Traer proveedores para el select
            cursor.execute("SELECT id_Proveedor, nombre_proveedor FROM Proveedores WHERE Activo = 1")
            proveedores = dictfetchall(cursor)
    except Exception:
        return redirect('productos_lista')

    return render(request, 'tienda/productos_editar.html', {
        'producto': producto,
        'proveedores': proveedores,
        'nombre_usuario': request.session.get('user_nombre'),
        'rol_usuario': request.session.get('user_rol')
    })

def productos_abastecer_view(request, id_prod):
    producto_info = None
    with connection.cursor() as cursor:
        # CORRECCIÓN: Usamos Nombre y Cantidad que son los nombres reales
        cursor.execute("""
            SELECT Id_Producto, Nombre, Cantidad 
            FROM Productos WHERE Id_Producto = %s
        """, [id_prod])
        row = cursor.fetchone()
        if row:
            producto_info = {
                'id': row[0],
                'nombre': row[1],
                'stock': row[2]
            }

    if request.method == 'POST':
        cantidad_ingresada = request.POST.get('cantidad_compra')
        if cantidad_ingresada:
            try:
                nueva_cantidad = int(cantidad_ingresada)
                with connection.cursor() as cursor:
                    # CORRECCIÓN: Actualizamos usando la columna Cantidad
                    cursor.execute("""
                        UPDATE Productos 
                        SET Cantidad = Cantidad + %s 
                        WHERE Id_Producto = %s
                    """, [nueva_cantidad, id_prod])
                
                messages.success(request, f" Stock actualizado para {producto_info['nombre']}")
                return redirect('reportes') 
            except Exception as e:
                messages.error(request, f"Error al actualizar: {e}")

    context = {
        'producto': producto_info,
        'nombre_usuario': request.session.get('user_nombre'),
    }
    return render(request, 'tienda/productos_abastecer.html', context)

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


def clientes_lista_view(request):
    # 1. Tu consulta SQL actual para traer los datos
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT c.Id_Cliente, c.Nombre, c.Apellido, c.correo, t.numero_telefono_C, c.Activo
            FROM Clientes c
            LEFT JOIN ClienteTelefono t ON c.Id_Cliente = t.id_cliente
        """)
        columns = [col[0] for col in cursor.description]
        rows = cursor.fetchall()

    clientes_formateados = []
    for row in rows:
        datos = dict(zip(columns, row))
        
        # --- EL TRUCO DEL GUION ESTÁ AQUÍ ---
        num = str(datos['numero_telefono_C'] or "").strip()
        if len(num) == 8:
            # Corta los primeros 4 dígitos, pone el guion y pega los otros 4
            datos['telefono_con_guion'] = f"{num[:4]}-{num[4:]}"
        else:
            datos['telefono_con_guion'] = num if num else "N/A"
            
        clientes_formateados.append(datos)

    return render(request, 'tienda/clientes_lista.html', {'clientes': clientes_formateados})

def clientes_agregar_view(request):
    if request.method == 'POST':
        nom = request.POST.get('nombre')
        ape = request.POST.get('apellido')
        cor = request.POST.get('correo')
        
        # LIMPPIAMOS EL GUION (ej: 8380-5501 -> 83805501)
        tel1 = request.POST.get('tel1', '').replace('-', '')
        tel2 = request.POST.get('tel2', '').replace('-', '')

        try:
            with transaction.atomic():
                # 1. ID Automático
                with connection.cursor() as cursor:
                    cursor.execute("SELECT ISNULL(MAX(Id_Cliente), 0) + 1 FROM Clientes")
                    nuevo_id = cursor.fetchone()[0]

                # 2. Guardar Cliente
                with connection.cursor() as cursor:
                    cursor.execute(
                        "INSERT INTO Clientes (Id_Cliente, Nombre, Apellido, correo, Activo, EsOcasional) VALUES (%s, %s, %s, %s, 1, 0)",
                        [nuevo_id, nom, ape, cor]
                    )

                # 3. Guardar Teléfonos en ClienteTelefono
                with connection.cursor() as cursor:
                    for num in [tel1, tel2]:
                        if num:
                            cursor.execute("SELECT ISNULL(MAX(id_telefonoCli), 0) + 1 FROM ClienteTelefono")
                            nuevo_id_tel = cursor.fetchone()[0]
                            cursor.execute(
                                "INSERT INTO ClienteTelefono (id_telefonoCli, id_cliente, numero_telefono_C) VALUES (%s, %s, %s)",
                                [nuevo_id_tel, nuevo_id, num]
                            )

            messages.success(request, f" Cliente guardado con éxito.")
            return redirect('clientes_lista')
        except Exception as e:
            messages.error(request, f"Error: {e}")

    return render(request, 'tienda/clientes_agregar.html')
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
        # 1. Capturamos datos y LIMPIAMOS el guion (8380-5501 -> 83805501)
        prov_nombre = request.POST.get('nombre_proveedor')
        prov_dir = request.POST.get('Direccion')
        prov_tel_1 = request.POST.get('numero_telefono_P_1', '').replace('-', '')
        prov_tel_2 = request.POST.get('numero_telefono_P_2', '').replace('-', '')
        prov_correo = request.POST.get('correo')

        # --- VALIDACIÓN DE CORREO (Tu lógica original) ---
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
                messages.error(request, f"El correo '{prov_correo}' no es válido.")
                return redirect('proveedores_lista')

        try:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    # 2. ID AUTOMÁTICO (MAX + 1)
                    cursor.execute("SELECT ISNULL(MAX(id_Proveedor), 0) + 1 FROM Proveedores")
                    prov_id = cursor.fetchone()[0]

                    # 3. Validar Nombre Duplicado
                    cursor.execute("SELECT COUNT(*) FROM Proveedores WHERE LOWER(nombre_proveedor) = LOWER(%s)", [prov_nombre.strip()])
                    if cursor.fetchone()[0] > 0:
                        messages.error(request, f"El proveedor '{prov_nombre}' ya existe.")
                        return redirect('proveedores_lista')

                    # 4. INSERT EN TABLA PROVEEDORES
                    sql_prov = "INSERT INTO Proveedores (id_Proveedor, nombre_proveedor, correo, Direccion, Activo) VALUES (%s, %s, %s, %s, 1)"
                    cursor.execute(sql_prov, [prov_id, prov_nombre, prov_correo, prov_dir])
                    
                    # 5. INSERT EN TABLA TELÉFONOS (Con ID automático de teléfono)
                    cursor.execute("SELECT ISNULL(MAX(id_telefonoProve), 0) FROM ProveedorTelefono")
                    next_id_tel = cursor.fetchone()[0] + 1
                    
                    if prov_tel_1:
                        cursor.execute("INSERT INTO ProveedorTelefono VALUES (%s, %s, %s)", [next_id_tel, prov_id, prov_tel_1])
                        next_id_tel += 1 
                    if prov_tel_2:
                        cursor.execute("INSERT INTO ProveedorTelefono VALUES (%s, %s, %s)", [next_id_tel, prov_id, prov_tel_2])
            
            messages.success(request, f"✅ Proveedor '{prov_nombre}' agregado con ID: {prov_id}")
            return redirect('proveedores_lista')
        except Exception as e:
            messages.error(request, f"Error al guardar: {e}")

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

def proveedores_lista_view(request):
    # Traemos los proveedores y sus teléfonos desde tus tablas de SQL Server
    sql = """
        SELECT 
            p.id_Proveedor, 
            p.nombre_proveedor, 
            p.correo, 
            p.Direccion,
            (SELECT TOP 1 numero_telefono FROM ProveedorTelefono WHERE id_Proveedor = p.id_Proveedor) as tel_db
        FROM Proveedores p
        WHERE p.Activo = 1
    """
    
    with connection.cursor() as cursor:
        cursor.execute(sql)
        columns = [col[0] for col in cursor.description]
        rows = cursor.fetchall()

    proveedores_formateados = []
    for row in rows:
        datos = dict(zip(columns, row))
        
        # --- EL TRUCO DEL GUION ---
        num = str(datos['tel_db'] or "").strip()
        if len(num) == 8:
            # Convierte 83805501 en 8380-5501
            datos['telefono_con_guion'] = f"{num[:4]}-{num[4:]}"
        else:
            datos['telefono_con_guion'] = num or "N/A"
            
        proveedores_formateados.append(datos)

    return render(request, 'tienda/proveedores_lista.html', {'proveedores': proveedores_formateados})
# ==========================================
#    ASIGNAR PROVEEDORES (COSTOS)
# ==========================================

@admin_requerido
@admin_requerido
def proveedor_producto_lista_view(request):
    # --- CAPTURAMOS EL PARÁMETRO 'q' QUE VIENE DE REPORTES ---
    search_query = request.GET.get('q', '') # <--- AGREGÁ ESTO
    
    mostrar_desactivados = request.GET.get('mostrar_desactivados')
    orden = request.GET.get('orden', 'nombre')
    
    try:
        with connection.cursor() as cursor:
            # Tu lógica de filtros ya usa search_query, así que con esto basta
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
            # Traemos solo los que están activos
            cursor.execute("SELECT Id_Producto, Nombre FROM Productos WHERE Activo = 1 ORDER BY Nombre")
            productos = dictfetchall(cursor)
            cursor.execute("SELECT id_Proveedor, nombre_proveedor FROM Proveedores WHERE Activo = 1 ORDER BY nombre_proveedor")
            proveedores = dictfetchall(cursor)
    except Exception as e: 
        print(f"Error cargando selects: {e}")

    if request.method == 'POST':
        id_prod = request.POST.get('id_producto')
        id_prov = request.POST.get('id_proveedor')
        precio = request.POST.get('precio_compra')
        cantidad = request.POST.get('cantidad_compra')

        try:
            with connection.cursor() as cursor:
                # Si ya existe la relación, la actualizamos; si no, la creamos
                cursor.execute("SELECT COUNT(*) FROM ProveedorProducto WHERE Id_Producto = %s AND Id_Proveedor = %s", [id_prod, id_prov])
                if cursor.fetchone()[0] > 0:
                    sql = "UPDATE ProveedorProducto SET PrecioCompra=%s, CantidadCompra=%s, Activo=1 WHERE Id_Producto=%s AND Id_Proveedor=%s"
                    cursor.execute(sql, [precio, cantidad, id_prod, id_prov])
                else:
                    sql = "INSERT INTO ProveedorProducto (Id_Producto, Id_Proveedor, PrecioCompra, CantidadCompra, Activo) VALUES (%s, %s, %s, %s, 1)"
                    cursor.execute(sql, [id_prod, id_prov, precio, cantidad])
            
            messages.success(request, "Costo y proveedor asignados correctamente.")
            return redirect('proveedor_producto_lista')
        except Exception as e:
            messages.error(request, f"Error al asignar costo: {e}")

    context = {
        'productos': productos,
        'proveedores': proveedores,
        'nombre_usuario': request.session.get('user_nombre'),
        'rol_usuario': request.session.get('user_rol'),
    }
    # ASEGÚRATE DE QUE LA RUTA SEA ESTA:
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
def facturacion_view(request):
    query = request.GET.get('q', '')
    
    # 1. Buscamos (Filtrar por nombre o ID)
    if query:
        productos_qs = Productos.objects.filter(
            Q(nombre__icontains=query) | Q(id_producto__icontains=query)
        ).filter(activo=True)
    else:
        productos_qs = Productos.objects.filter(activo=True)

    # 2. Convertimos a Diccionario (CORRIGIENDO LA FOTO)
    productos_list = []
    for p in productos_qs:
        
        url_foto = ""
        if p.rutafoto:
            # --- CORRECCIÓN DE IMAGEN ---
            # Si el nombre del archivo ya empieza con "/media/", lo usamos tal cual.
            # Si no, dejamos que Django construya la URL completa.
            nombre_archivo = str(p.rutafoto)
            if nombre_archivo.startswith('/media/') or nombre_archivo.startswith('media/'):
                url_foto = nombre_archivo # Ya tiene la ruta, no agregamos nada
            elif nombre_archivo.startswith('/static/') or nombre_archivo.startswith('static/'):
                url_foto = nombre_archivo # Es estática, la dejamos igual
            else:
                # Caso normal: Django le agrega la ruta de medios
                try:
                    url_foto = p.rutafoto.url
                except:
                    url_foto = "" # Por si acaso falla
        
        # Diccionario con MAYÚSCULAS (para que tu HTML no se rompa)
        p_dict = {
            'Id_Producto': p.id_producto,
            'Nombre': p.nombre,
            'PrecioVenta': p.precioventa,
            'Cantidad': p.cantidad,
            'rutaFoto': url_foto, 
        }
        productos_list.append(p_dict)

    # 3. Datos del carrito y clientes
    carrito = request.session.get('carrito', [])
    total_carrito = sum(Decimal(str(item.get('subtotal', 0))) for item in carrito)
    
    # Clientes
    clientes_list = list(Clientes.objects.filter(activo=True).values('id_cliente', 'nombre', 'apellido'))

    context = {
        'productos': productos_list, # Pasamos nuestra lista corregida
        'clientes': clientes_list,
        'carrito': carrito,
        'total_carrito': total_carrito,
    }

    return render(request, 'tienda/facturacion.html', context)

def facturacion_agregar_item(request):
    if request.method == 'POST':
        id_producto = request.POST.get('id_producto')
        
        # Obtenemos el producto usando el ID que viene del HTML
        producto = get_object_or_404(Productos, pk=id_producto)
        
        # Recuperamos el carrito actual
        carrito = request.session.get('carrito', [])
        
        # Verificamos si ya existe en el carrito para solo sumar cantidad
        encontrado = False
        for item in carrito:
            if item['id'] == producto.pk:
                # Chequeamos si hay stock suficiente
                if item['cantidad'] + 1 <= producto.cantidad:
                    item['cantidad'] += 1
                    # Recalculamos subtotal
                    item['subtotal'] = float(item['precio']) * item['cantidad']
                    encontrado = True
                else:
                    messages.warning(request, f"Solo hay {producto.cantidad} unidades de {producto.nombre}")
                    encontrado = True # Para que no intente agregarlo como nuevo
                break
        
        # Si no estaba en el carrito, lo creamos nuevo
        if not encontrado:
            if producto.cantidad > 0:
                # Validamos la imagen para que no de error si no tiene
                url_imagen = ""
                if producto.rutafoto:
                    url_imagen = producto.rutafoto.url
                
                nuevo_item = {
                    'id': producto.pk,
                    'nombre': producto.nombre,  # Tu modelo usa 'nombre' (minúscula)
                    'precio': float(producto.precioventa), # Tu modelo usa 'precioventa' (todo junto)
                    'cantidad': 1,
                    'subtotal': float(producto.precioventa),
                    'imagen': url_imagen
                }
                carrito.append(nuevo_item)
            else:
                messages.error(request, "Producto agotado.")

        # Guardamos los cambios en la sesión
        request.session['carrito'] = carrito
        request.session.modified = True
        
    return redirect('facturacion_view')

# --- AUTOCOMPRA (SOY YO) ---
@login_requerido
def autocompra_view(request):
    nombre_usuario = request.session.get('user_nombre', 'Usuario')
    apellido_fijo = "(Personal)" # Para diferenciar tu perfil de cliente

    try:
        with transaction.atomic():
            with connection.cursor() as cursor:
                # 1. Buscar si ya existe tu perfil de cliente
                cursor.execute("SELECT Id_Cliente FROM Clientes WHERE Nombre = %s AND Apellido = %s", [nombre_usuario, apellido_fijo])
                fila = cursor.fetchone()

                if fila:
                    id_cliente = fila[0]
                else:
                    # 2. Si no existe, crearlo (Buscamos el ID más alto disponible)
                    cursor.execute("SELECT ISNULL(MAX(Id_Cliente), 0) + 1 FROM Clientes")
                    id_cliente = cursor.fetchone()[0]
                    
                    sql_ins = "INSERT INTO Clientes (Id_Cliente, Nombre, Apellido, Correo, Activo, EsOcasional) VALUES (%s, %s, %s, 'N/A', 1, 0)"
                    cursor.execute(sql_ins, [id_cliente, nombre_usuario, apellido_fijo])

        messages.success(request, f"Modo Auto Compra activado para: {nombre_usuario}")
        # Redirigimos a la facturación pasando tu ID por la URL para que se seleccione solo
        return redirect(f'/facturacion/?cliente_seleccionado={id_cliente}')

    except Exception as e:
        messages.error(request, f"Error en auto compra: {e}")
        return redirect('facturacion_view')

def facturacion_eliminar_item(request, item_index):
    carrito = request.session.get('carrito', [])
    
    if 0 <= item_index < len(carrito):
        del carrito[item_index]
        request.session['carrito'] = carrito
        request.session.modified = True
        messages.success(request, "Producto eliminado del carrito.")
        
    return redirect('facturacion_view')



def facturacion_guardar_view(request):
    if request.method == 'POST':
        carrito = request.session.get('carrito', [])
        
        if not carrito:
            messages.error(request, "El carrito está vacío.")
            return redirect('facturacion_view')

        try:
            with transaction.atomic():
                # --- 1. LÓGICA DE CLIENTE AUTOMÁTICO ---
                cliente_id = request.POST.get('cliente_id')
                
                if cliente_id:
                    # Si el cajero eligió a alguien, usamos ese
                    cliente_obj = get_object_or_404(Clientes, pk=cliente_id)
                else:
                    # Si lo dejó vacío, buscamos al "Cliente Particular"
                    cliente_obj = Clientes.objects.filter(nombre__icontains="Particular").first()
                    
                    # Plan B: Si no existe "Particular", busca "General"
                    if not cliente_obj:
                         cliente_obj = Clientes.objects.filter(nombre__icontains="General").first()
                    
                    if not cliente_obj:
                        messages.error(request, "⚠ Error: No seleccionaste cliente y no existe el 'Cliente Particular' en la BD.")
                        return redirect('facturacion_view')

                # --- 2. TOTALES (CON PROTECCIÓN ANTI-VACÍOS) ---
                # Obtenemos lo que se escribió en Envío. Si está vacío, devuelve cadena vacía ''
                envio_texto = request.POST.get('costo_envio', '').strip()
                
                # Si envio_texto tiene algo, lo convierte a Decimal. Si está vacío, usa '0'.
                costo_envio = Decimal(envio_texto if envio_texto else '0')

                # Sumamos el total de productos del carrito
                total_productos = sum(Decimal(str(item.get('subtotal', 0))) for item in carrito)
                total_final = total_productos + costo_envio

                # --- 3. CALCULAR ID MANUAL (Para tu tabla histórica) ---
                ultimo_id = Facturas.objects.aggregate(Max('Id_Factura'))['Id_Factura__max']
                
                # Si es la primera venta de la historia es la 1, si no, le sumamos 1
                nuevo_id = 1 if ultimo_id is None else ultimo_id + 1

                # --- 4. CREAR FACTURA ---
                nueva_factura = Facturas.objects.create(
                    Id_Factura=nuevo_id,
                    Cliente=cliente_obj,
                    Total=total_final,
                    CostoEnvio=costo_envio,
                    # Descomenta la siguiente línea si tu base de datos exige un usuario:
                    # Id_Usuario = 1 
                )

                # --- 5. GUARDAR DETALLES Y RESTAR STOCK ---
                for item in carrito:
                    pid = item.get('id') or item.get('id_producto')
                    producto_real = Productos.objects.get(pk=pid)
                    
                    cantidad = int(item.get('cantidad', 1))
                    subtotal = Decimal(str(item.get('subtotal', 0)))

                    DetalleFactura.objects.create(
                        Factura=nueva_factura,
                        Producto=producto_real,
                        Cantidad=cantidad,
                        Subtotal=subtotal
                    )

                    # Restar del inventario
                    producto_real.cantidad -= cantidad
                    producto_real.save()

                # --- 6. FINALIZAR ---
                request.session['carrito'] = [] 
                request.session.modified = True
                
                # ¡Éxito! Nos vamos directo al ticket
                return redirect('factura_recibo', id_factura=nueva_factura.Id_Factura)

        except Exception as e:
            print(f" ERROR AL COBRAR: {e}")
            messages.error(request, f"Error al guardar la venta: {e}")
            return redirect('facturacion_view')
    
    return redirect('facturacion_view')

def facturacion_restar_item(request, item_index):
    carrito = request.session.get('carrito', [])
    
    if 0 <= item_index < len(carrito):
        item = carrito[item_index]
        
        if item['cantidad'] > 1:
            item['cantidad'] -= 1
            item['subtotal'] = float(item['precio']) * item['cantidad']
            request.session.modified = True
        else:
            # Opcional: Si llega a 1 y le das restar, ¿quieres borrarlo? 
            # Por ahora solo no hace nada si es 1.
            pass
            
    return redirect('facturacion_view')

def facturacion_sumar_item(request, item_index):
    carrito = request.session.get('carrito', [])
    
    if 0 <= item_index < len(carrito):
        item = carrito[item_index]
        
        # CORRECCIÓN: Usamos 'id' (que es como lo guardamos ahora)
        prod_id = item.get('id') 
        
        # Consultamos a la base de datos para ver si hay stock real
        producto = get_object_or_404(Productos, pk=prod_id)
        
        # Validamos Stock
        if item['cantidad'] + 1 <= producto.cantidad:
            item['cantidad'] += 1
            item['subtotal'] = float(item['precio']) * item['cantidad']
            request.session.modified = True
        else:
            messages.warning(request, f"✋ Solo quedan {producto.cantidad} unidades de {producto.nombre}")
            
    return redirect('facturacion_view')

@login_requerido
def factura_recibo_view(request, id_fact):
    # Esta vista SÓLO sirve para MOSTRAR la factura guardada
    try:
        with connection.cursor() as cursor:
            # Traemos la factura (Usamos F.* para traer todos los campos)
            cursor.execute("""
                SELECT F.id_factura, F.FechaHora, F.Total, F.MontoPagado, F.Cambio, F.CostoEnvio, 
                       C.Nombre AS ClienteNombre, U.Nombre AS CajeroNombre 
                FROM Factura F 
                JOIN Clientes C ON F.id_cliente = C.Id_Cliente
                JOIN Usuarios U ON F.Id_Usuario = U.IdUsuario
                WHERE F.id_factura = %s""", [id_fact])
            factura = dictfetchall(cursor)[0]

            cursor.execute("""
                SELECT D.Cantidad, D.Subtotal, P.Nombre AS ProductoNombre 
                FROM DetalleFactura D 
                JOIN Productos P ON D.Id_Producto = P.Id_Producto 
                WHERE D.id_factura = %s""", [id_fact])
            detalles = dictfetchall(cursor)

            # Cálculo de subtotal de productos para que no salga vacío
            sub_productos = Decimal(factura['Total']) - Decimal(factura['CostoEnvio'] or 0)

        return render(request, 'tienda/factura_recibo.html', {
            'factura': factura,
            'detalles': detalles,
            'subtotal_productos': sub_productos
        })
    except:
        return redirect('facturacion_view')

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

#recuperacion de cuenta
def recuperar_password_view(request):
    if request.method == 'POST':
        correo = request.POST.get('correo')
        
        try:
            with connection.cursor() as cursor:
                # 1. Buscar usuario
                cursor.execute("SELECT IdUsuario, Nombre FROM Usuarios WHERE Correo = %s", [correo])
                usuario = cursor.fetchone()
                
                if usuario:
                    user_id, nombre = usuario[0], usuario[1]
                    token = str(uuid.uuid4()) # Generamos el token único
                    
                    # 2. Guardar token en BD
                    cursor.execute("UPDATE Usuarios SET token_recuperacion = %s WHERE IdUsuario = %s", [token, user_id])
                    
                    # 3. Preparar el link
                    link = request.build_absolute_uri(reverse('cambiar_password', args=[token]))
                    
                    # 4. ENVIAR EL CORREO
                    asunto = 'Recuperación de Contraseña - Mi Tiendita'
                    mensaje = f'Hola {nombre},\n\nPara cambiar tu clave, hacé clic aquí:\n{link}'
                    
                    send_mail(
                        asunto,
                        mensaje,
                        settings.DEFAULT_FROM_EMAIL,
                        [correo],
                        fail_silently=False,
                    )
                    
                    messages.success(request, f"Se ha enviado un enlace a {correo}.")
                    return redirect('login')
                else:
                    messages.error(request, "Ese correo electrónico no está registrado.")
        except Exception as e:
            messages.error(request, "Error al enviar el correo. Verificá tu conexión.")

    return render(request, 'tienda/password_reset_form.html')


# --- VISTA 2: CAMBIAR LA CONTRASEÑA ---
def cambiar_password_view(request, token):
    # 1. Validar si el token existe
    usuario_valido = None
    try:
        with connection.cursor() as cursor:
            # Usamos IdUsuario
            cursor.execute("SELECT IdUsuario, Nombre FROM Usuarios WHERE token_recuperacion = %s", [token])
            usuario_valido = cursor.fetchone()
    except Exception as e:
        print(e)

    if not usuario_valido:
        messages.error(request, "El enlace es inválido o ya expiró.")
        return redirect('login')

    # 2. Procesar el cambio de contraseña
    if request.method == 'POST':
        nueva_pass = request.POST.get('password')
        confirm_pass = request.POST.get('confirm_password')
        
        if nueva_pass != confirm_pass:
            messages.error(request, "Las contraseñas no coinciden.")
        else:
            try:
                # Encriptamos la contraseña
                hash_pass = make_password(nueva_pass)
                
                with connection.cursor() as cursor:
                    # OJO: Actualizamos Contraseña (con Ñ) y borramos el token
                    sql = """
                        UPDATE Usuarios 
                        SET Contraseña = %s, token_recuperacion = NULL 
                        WHERE token_recuperacion = %s
                    """
                    cursor.execute(sql, [hash_pass, token])
                    
                messages.success(request, "¡Contraseña restablecida! Ahora podés iniciar sesión.")
                return redirect('login')
            except Exception as e:
                messages.error(request, f"Error al guardar: {e}")

    return render(request, 'tienda/password_change_form.html', {'token': token})

def facturacion_nueva_venta(request):
    """Limpia el carrito de la sesión."""
    if 'carrito' in request.session:
        request.session['carrito'] = []
        request.session.modified = True
    return redirect('facturacion_view')

def factura_recibo(request, id_factura):
    factura = get_object_or_404(Facturas, pk=id_factura)
    detalles = DetalleFactura.objects.filter(Factura=factura)
    return render(request, 'tienda/factura_recibo.html', {'factura': factura, 'detalles': detalles})

def buscar_producto_ajx(request):
    termino = request.GET.get('term', '')  # Lo que el usuario escribe
    productos = []
    
    if termino:
        with connection.cursor() as cursor:
            # Buscamos por nombre o por ID del producto
            query = """
                SELECT id_Producto, nombre_producto, precio_venta 
                FROM Productos 
                WHERE nombre_producto LIKE %s OR CAST(id_Producto AS VARCHAR) LIKE %s
                AND Activo = 1
            """
            cursor.execute(query, [f'%{termino}%', f'%{termino}%'])
            rows = cursor.fetchall()
            
            for row in rows:
                productos.append({
                    'id': row[0],
                    'label': f"{row[1]} (ID: {row[0]})",  # Lo que sale en la lista
                    'value': row[1],                    # Lo que queda en el input
                    'precio': str(row[2])               # Para autollenar el precio
                })
                
    return JsonResponse(productos, safe=False)

