from django.http import HttpResponse
from django.template.loader import get_template
from xhtml2pdf import pisa
import json
import uuid
import datetime
from decimal import Decimal
from django.utils import timezone
from datetime import timedelta
from django.contrib import messages
from django.shortcuts import redirect


from django.db.models.functions import TruncMonth, TruncDate
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction, connection
from django.db.models import Sum, Max, Q, F, Count
from django.db.models.functions import TruncMonth
from django.utils import timezone
from django.contrib.auth.hashers import make_password
from django.core.files.storage import FileSystemStorage
from django.core.mail import send_mail
from django.urls import reverse
from django.conf import settings
from django.http import JsonResponse

# Importación de modelos
from .models import (
    Productos, Clientes, Proveedores, ProveedorProducto,
    Facturas, DetalleFactura, ClienteTelefono, ProveedorTelefono,
    Egresos, CajaDiaria,ClienteIdentidad
)

# ==========================================
#              HERRAMIENTAS & DECORADORES
# ==========================================

def dictfetchall(cursor):
    """Convierte filas de SQL a diccionarios."""
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]

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

# ==========================================
#              DASHBOARD & REPORTES
# ==========================================

@login_requerido
def dashboard_view(request):
    # 1. Contadores
    num_clientes = Clientes.objects.filter(activo=True, esocasional=False).count()
    num_productos = Productos.objects.filter(activo=True).count()
    num_proveedores = Proveedores.objects.filter(activo=True).count()

    # 2. Gráfica Top 5
    top5_query = (DetalleFactura.objects
                  .values('id_producto__nombre')
                  .annotate(TotalVendido=Sum('Cantidad'))
                  .order_by('-TotalVendido')[:5])

    labels = [item['id_producto__nombre'] for item in top5_query]
    data = [item['TotalVendido'] for item in top5_query]

    # 3. Alerta Stock BAJO (Productos que necesitan reabastecimiento)
    # Esto trae los productos con cantidad <= stockminimo
    productos_bajos = Productos.objects.filter(
        cantidad__lte=F('stockminimo'), 
        activo=True
    ).order_by('cantidad')  # Ordenar por cantidad ascendente (los más críticos primero)
    
    # 4. Alerta Stock AGOTADOS (Cantidad = 0)
    productos_agotados = Productos.objects.filter(
        cantidad=0, 
        activo=True
    ).order_by('nombre')

    context = {
        'nombre_usuario': request.session.get('user_nombre'),
        'rol_usuario': request.session.get('user_rol'),
        'total_clientes': num_clientes,
        'total_productos': num_productos,
        'total_proveedores': num_proveedores,
        'chart_labels': json.dumps(labels),
        'chart_data': json.dumps(data),
        'productos_bajos': productos_bajos,
        'productos_agotados': productos_agotados,  # Nueva variable
    }
    return render(request, 'tienda/dashboard.html', context)

@login_requerido
def reportes_view(request):
    hoy = timezone.now().date()
    mes_actual = hoy.month
    anio_actual = hoy.year

    # 1. Ventas Hoy y Mes (Aquí SÍ sumamos Fiado porque es Venta Bruta)
    venta_hoy = Facturas.objects.filter(FechaHora__date=hoy, anulada=False).aggregate(Sum('Total'))['Total__sum'] or 0
    venta_mes = Facturas.objects.filter(FechaHora__year=anio_actual, FechaHora__month=mes_actual, anulada=False).aggregate(Sum('Total'))['Total__sum'] or 0

    # 2. Stock Bajo
    lista_bajos_stock = Productos.objects.filter(cantidad__lte=F('stockminimo'), activo=True)
    bajos_stock = lista_bajos_stock.count()

    # 3. Ganancias Productos
    tabla_ganancias = []
    total_ganancia_mes = 0

    detalles_mes = DetalleFactura.objects.filter(
        id_factura__FechaHora__year=anio_actual,
        id_factura__FechaHora__month=mes_actual,
        id_factura__anulada=False
    ).values('id_producto__id_producto', 'id_producto__nombre').annotate(vendidos=Sum('Cantidad'), ingreso_total=Sum('Subtotal')).order_by('-ingreso_total')

    for item in detalles_mes:
        p_id = item['id_producto__id_producto']
        nombre = item['id_producto__nombre']
        vendidos = item['vendidos']
        ingreso = float(item['ingreso_total'])

        costo_unitario = 0
        pp = ProveedorProducto.objects.filter(producto_id=p_id, activo=True).first()
        if pp and pp.cantidadcompra > 0:
            costo_unitario = float(pp.preciocompra) / float(pp.cantidadcompra)

        costo_total_venta = costo_unitario * vendidos
        ganancia_neta = ingreso - costo_total_venta
        total_ganancia_mes += ganancia_neta

        tabla_ganancias.append({
            'nombre': nombre, 'vendidos': vendidos, 'ingreso': f"{ingreso:,.2f}",
            'costo_aprox': f"{costo_total_venta:,.2f}", 'ganancia': f"{ganancia_neta:,.2f}"
        })

    # 4. Sumar Envíos a la ganancia
    try:
        envios = Facturas.objects.filter(FechaHora__year=anio_actual, FechaHora__month=mes_actual, CostoEnvio__gt=0, anulada=False).aggregate(num=Count('id_factura'), total=Sum('CostoEnvio'))
        if envios['total']:
            total_ganancia_mes += float(envios['total'])
            tabla_ganancias.insert(0, {'nombre': '🛵 Servicio de Delivery', 'vendidos': envios['num'], 'ingreso': f"{envios['total']:,.2f}", 'costo_aprox': "0.00", 'ganancia': f"{envios['total']:,.2f}"})
    except: pass

    # 5. CAJA REAL (Dinero Físico)
    # IMPORTANTE: Aquí NO sumamos las ventas al fiado (en_deuda=False)
    dinero_caja_texto = "C$ 0.00"
    try:
        caja_actual = CajaDiaria.objects.filter(activa=True).last()
        if caja_actual:
            ventas_turno = Facturas.objects.filter(
                FechaHora__gte=caja_actual.fecha_apertura,
                anulada=False,
                en_deuda=False  # <--- ESTA LÍNEA ES LA CLAVE
            ).aggregate(Sum('Total'))['Total__sum'] or 0

            gastos_turno = Egresos.objects.filter(fecha__gte=caja_actual.fecha_apertura).aggregate(Sum('monto'))['monto__sum'] or 0
            saldo_fisico = float(caja_actual.monto_inicial) + float(ventas_turno) - float(gastos_turno)
            dinero_caja_texto = f"C$ {saldo_fisico:,.2f}"
        else:
            dinero_caja_texto = "🔴 Cerrada"
    except: pass

    # 6. Historial Mes a Mes (Flujo Neto)
    historial = {}
    with connection.cursor() as cursor:
        cursor.execute("SELECT strftime('%Y-%m', FechaHora) as Mes, SUM(Total) FROM tienda_facturas WHERE anulada=0 GROUP BY Mes")
        for r in cursor.fetchall():
            if r[0]: historial[r[0]] = {'ingreso': float(r[1]), 'gasto': 0}
        cursor.execute("SELECT strftime('%Y-%m', fecha) as Mes, SUM(monto) FROM tienda_egresos GROUP BY Mes")
        for r in cursor.fetchall():
            if r[0]:
                if r[0] not in historial: historial[r[0]] = {'ingreso': 0, 'gasto': 0}
                historial[r[0]]['gasto'] = float(r[1])
    tabla_historial = []
    for k in sorted(historial.keys(), reverse=True):
        d = historial[k]
        tabla_historial.append({'mes': k, 'ingreso': f"{d['ingreso']:,.2f}", 'gasto': f"{d['gasto']:,.2f}", 'balance': f"{(d['ingreso']-d['gasto']):,.2f}", 'es_positivo': (d['ingreso']-d['gasto']) >= 0})

    # 7. Historial Diario (Ventas Día por Día)
    ventas_por_dia = []
    try:
        qs_diario = (Facturas.objects
                     .filter(anulada=False)
                     .annotate(dia=TruncDate('FechaHora'))
                     .values('dia')
                     .annotate(total_dia=Sum('Total'), num_ventas=Count('id_factura'))
                     .order_by('-dia'))
        for v in qs_diario:
            ventas_por_dia.append({
                'fecha': v['dia'],
                'tickets': v['num_ventas'],
                'total': f"{float(v['total_dia']):,.2f}"
            })
    except Exception as e: print(f"Error diario: {e}")

    # 8. Historial de Cierres de Caja
    historial_cajas = CajaDiaria.objects.filter(activa=False).order_by('-fecha_cierre')

    g_items = [x for x in tabla_ganancias if x['nombre'] != '🛵 Servicio de Delivery'][:5]
    context = {
        'venta_hoy': venta_hoy, 'venta_mes': venta_mes, 'ganancia_mes': f"{total_ganancia_mes:,.2f}",
        'dinero_caja': dinero_caja_texto, 'bajos_stock': bajos_stock, 'lista_bajos_stock': lista_bajos_stock,
        'tabla_ganancias': tabla_ganancias,
        'tabla_historial': tabla_historial,
        'ventas_por_dia': ventas_por_dia,
        'historial_cajas': historial_cajas,
        'labels_prod_json': json.dumps([i['nombre'] for i in g_items] or ["Sin ventas"]),
        'data_prod_json': json.dumps([i['vendidos'] for i in g_items] or [0]),
        'nombre_usuario': request.session.get('user_nombre'), 'rol_usuario': request.session.get('user_rol'),
    }
    return render(request, 'tienda/reportes.html', context)

# ==========================================
#              PRODUCTOS
# ==========================================

@login_requerido
def productos_view(request):
    search_query = request.GET.get('q', '')
    mostrar_desactivados = request.GET.get('mostrar_desactivados')

    if search_query:
        if mostrar_desactivados:
            productos = Productos.objects.filter(Q(nombre__icontains=search_query) | Q(id_producto__icontains=search_query))
        else:
            productos = Productos.objects.filter(Q(nombre__icontains=search_query) | Q(id_producto__icontains=search_query), activo=True)
    else:
        if mostrar_desactivados:
            productos = Productos.objects.all()
        else:
            productos = Productos.objects.filter(activo=True)

    productos_list = []
    for p in productos:
        prov_nombre = "Sin Asignar"
        costo_display = 0
        if p.idproveedor:
            prov_nombre = p.idproveedor.nombre_proveedor
            pp = ProveedorProducto.objects.filter(producto=p, proveedor=p.idproveedor).first()
            if pp:
                costo_display = pp.preciocompra

        productos_list.append({
            'Id_Producto': p.id_producto,
            'Nombre': p.nombre,
            'PrecioVenta': p.precioventa,
            'Cantidad': p.cantidad,
            'StockMinimo': p.stockminimo,
            'Activo': p.activo,
            'ProveedorNombre': prov_nombre,
            'Costo': costo_display,
            'PrecioCosto': costo_display
        })

    context = {
        'nombre_usuario': request.session.get('user_nombre'),
        'rol_usuario': request.session.get('user_rol'),
        'productos': productos_list,
        'search_query': search_query,
        'mostrando_desactivados': bool(mostrar_desactivados)
    }
    return render(request, 'tienda/productos.html', context)
from django.http import JsonResponse
import json

# 1. NUEVA VISTA: Guarda el borrador en la sesión en tiempo real cada vez que escriben
@login_requerido
def guardar_borrador_producto_view(request):
    if request.method == 'POST':
        try:
            datos = json.loads(request.body)
            # Guardamos el diccionario completo del borrador en la sesión
            request.session['borrador_producto'] = datos
            request.session.modified = True
            return JsonResponse({'status': 'ok'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    return JsonResponse({'status': 'invalid_method'}, status=405)


# 2. VISTA ACTUALIZADA: Tu función con la carga e inyección del borrador
@login_requerido
def productos_agregar_view(request):
    if request.method == 'POST':
        try:
            nombre = request.POST.get('nombre')
            precio_venta = request.POST.get('precio_venta')
            stock_inicial = request.POST.get('cantidad')
            stock_min = request.POST.get('stock_min')
            id_prov = request.POST.get('id_proveedor')

            # Costos
            precio_compra = request.POST.get('precio_compra')
            cantidad_compra = request.POST.get('cantidad_compra') or 1

            ruta_foto = None
            if 'foto' in request.FILES:
                fs = FileSystemStorage()
                filename = fs.save(request.FILES['foto'].name, request.FILES['foto'])
                ruta_foto = fs.url(filename)

            with transaction.atomic():
                ultimo = Productos.objects.aggregate(Max('id_producto'))['id_producto__max']
                nuevo_id = 1 if ultimo is None else ultimo + 1

                prov_obj = None
                if id_prov:
                    # NOTA: Asegúrate si en tu modelo es id_proveedor o idproveedor
                    prov_obj = Proveedores.objects.get(pk=id_prov)

                nuevo_prod = Productos.objects.create(
                    id_producto=nuevo_id, nombre=nombre, precioventa=precio_venta,
                    cantidad=stock_inicial, stockminimo=stock_min,
                    idproveedor=prov_obj, rutafoto=ruta_foto, activo=True
                )

                if id_prov and precio_compra:
                    ProveedorProducto.objects.create(
                        producto=nuevo_prod,
                        proveedor=prov_obj,
                        preciocompra=precio_compra,
                        cantidadcompra=cantidad_compra,
                        activo=True
                    )

            # ✅ ÉXITO: Como ya se guardó el producto real, eliminamos el borrador temporal de la sesión
            if 'borrador_producto' in request.session:
                del request.session['borrador_producto']

            messages.success(request, f"¡Producto '{nombre}' creado con éxito!")
            return redirect('productos_lista')
        except Exception as e:
            messages.error(request, f"Error al guardar: {e}")

    # --- PROCESO PARA CARGAR EL BORRADOR (Si es un método GET) ---
    prov_objs = Proveedores.objects.filter(activo=True)
    proveedores = [{'id_Proveedor': p.id_proveedor, 'nombre_proveedor': p.nombre_proveedor} for p in prov_objs]
    
    # Extraemos el borrador si existe en la sesión actual, si no, mandamos un diccionario vacío
    borrador = request.session.get('borrador_producto', {})

    return render(request, 'tienda/productos_agregar.html', {
        'proveedores': proveedores,
        'borrador': borrador  # ✅ Pasamos el borrador al HTML
    })
@admin_requerido
def productos_editar_view(request, id_prod):
    producto = get_object_or_404(Productos, pk=id_prod)

    if request.method == 'POST':
        producto.nombre = request.POST.get('Nombre')
        producto.precioventa = request.POST.get('PrecioVenta')
        producto.cantidad = request.POST.get('Cantidad')
        producto.stockminimo = request.POST.get('StockMinimo')
        id_prov = request.POST.get('id_proveedor')

        if id_prov:
            producto.idproveedor = Proveedores.objects.get(pk=id_prov)
        else:
            producto.idproveedor = None

        if 'foto_del_producto' in request.FILES:
            fs = FileSystemStorage()
            filename = fs.save(request.FILES['foto_del_producto'].name, request.FILES['foto_del_producto'])
            producto.rutafoto = fs.url(filename)

        producto.save()

        precio_costo = request.POST.get('precio_compra')
        cantidad_compra = request.POST.get('cantidad_compra')

        if id_prov and precio_costo:
            pp = ProveedorProducto.objects.filter(producto=producto, proveedor_id=id_prov).first()
            if pp:
                pp.preciocompra = precio_costo
                pp.cantidadcompra = cantidad_compra or 1
                pp.activo = True
                pp.save()
            else:
                ProveedorProducto.objects.create(
                    producto=producto, proveedor_id=id_prov,
                    preciocompra=precio_costo, cantidadcompra=cantidad_compra or 1,
                    activo=True
                )

        messages.success(request, "Producto actualizado correctamente.")
        return redirect('productos_lista')

    prov_objs = Proveedores.objects.filter(activo=True)
    proveedores = [{'id_Proveedor': p.id_proveedor, 'nombre_proveedor': p.nombre_proveedor} for p in prov_objs]

    costo_actual = ""
    cant_compra_actual = 1
    if producto.idproveedor:
        pp = ProveedorProducto.objects.filter(producto=producto, proveedor=producto.idproveedor).first()
        if pp:
            costo_actual = pp.preciocompra
            cant_compra_actual = pp.cantidadcompra

    p_dict = {
        'Id_Producto': producto.id_producto,
        'Nombre': producto.nombre,
        'PrecioVenta': producto.precioventa,
        'Cantidad': producto.cantidad,
        'StockMinimo': producto.stockminimo,
        'rutaFoto': producto.rutafoto,
        'IdProveedor': producto.idproveedor.id_proveedor if producto.idproveedor else '',
        'PrecioCompra': costo_actual,
        'CantidadCompra': cant_compra_actual
    }

    return render(request, 'tienda/productos_editar.html', {
        'producto': p_dict,
        'proveedores': proveedores,
        'nombre_usuario': request.session.get('user_nombre'),
        'rol_usuario': request.session.get('user_rol')
    })

@admin_requerido
def productos_eliminar_view(request, id_prod):
    try:
        p = get_object_or_404(Productos, pk=id_prod)
        p.activo = False
        p.save()
        messages.success(request, "Producto desactivado.")
    except Exception as e: messages.error(request, f"Error: {e}")
    return redirect('productos_lista')

@admin_requerido
def productos_reactivar_view(request, id_prod):
    try:
        p = get_object_or_404(Productos, pk=id_prod)
        p.activo = True
        p.save()
        messages.success(request, "Producto reactivado.")
    except Exception as e: messages.error(request, f"Error: {e}")
    return redirect('productos_lista')

def productos_abastecer_view(request, id_prod):
    producto = get_object_or_404(Productos, pk=id_prod)
    if request.method == 'POST':
        cantidad_ingresada = request.POST.get('cantidad_compra')
        if cantidad_ingresada:
            try:
                nueva_cantidad = int(cantidad_ingresada)
                producto.cantidad += nueva_cantidad
                producto.save()
                messages.success(request, f"Stock actualizado.")
                return redirect('reportes_view')
            except Exception as e: messages.error(request, f"Error: {e}")
    return render(request, 'tienda/productos_abastecer.html', {
        'producto': {'id': producto.id_producto, 'nombre': producto.nombre, 'stock': producto.cantidad},
        'nombre_usuario': request.session.get('user_nombre')
    })

def buscar_producto_ajx(request):
    termino = request.GET.get('term', '')
    productos = []
    if termino:
        qs = Productos.objects.filter(Q(nombre__icontains=termino) | Q(id_producto__icontains=termino), activo=True)
        for p in qs:
            productos.append({'id': p.id_producto, 'label': f"{p.nombre} (ID: {p.id_producto})", 'value': p.nombre, 'precio': str(p.precioventa)})
    return JsonResponse(productos, safe=False)

# ==========================================
#              CLIENTES
# ==========================================

@login_requerido
def clientes_view(request):
    search_query = request.GET.get('q', '')
    mostrar_desactivados = request.GET.get('mostrar_desactivados')
    qs = Clientes.objects.filter(esocasional=False)

    if not mostrar_desactivados:
        qs = qs.filter(activo=True)
    if search_query:
        qs = qs.filter(Q(nombre__icontains=search_query) | Q(apellido__icontains=search_query))

    clientes_list = []
    for c in qs:
        tels = ClienteTelefono.objects.filter(id_cliente=c)
        str_tels = ", ".join([t.numero_telefono_c for t in tels])
        
        # 🛡️ VERIFICACIÓN DE SEGURIDAD: ¿Tiene fotos de identidad arriba?
        tiene_id = ClienteIdentidad.objects.filter(cliente=c).exists()
        identidad_obj = ClienteIdentidad.objects.filter(cliente=c).first()
        
        clientes_list.append({
            'Id_Cliente': c.id_cliente, 
            'Nombre': c.nombre, 
            'Apellido': c.apellido,
            'correo': c.correo, 
            'Activo': c.activo, 
            'Telefonos': str_tels,
            'Tiene_Identidad': tiene_id,
            # Pasamos las URLs de las imágenes por si querés mostrarlas en un ojito
            'foto_frontal': identidad_obj.foto_frontal.url if tiene_id and identidad_obj.foto_frontal else None,
            'foto_trasera': identidad_obj.foto_trasera.url if tiene_id and identidad_obj.foto_trasera else None,
        })

    context = {
        'nombre_usuario': request.session.get('user_nombre'), 
        'rol_usuario': request.session.get('user_rol'), 
        'clientes': clientes_list, 
        'search_query': search_query, 
        'mostrando_desactivados': bool(mostrar_desactivados)
    }
    return render(request, 'tienda/clientes.html', context)


@login_requerido
def cargar_identidad_view(request):
    """ Vista dedicada para subir o actualizar las fotos de la cédula """
    if request.method == 'POST':
        id_cli = request.POST.get('cliente_id')
        cliente = get_object_or_404(Clientes, pk=id_cli)
        
        # Ojo: En Django los archivos que vienen de formularios se leen en request.FILES
        frontal = request.FILES.get('foto_frontal')
        trasera = request.FILES.get('foto_trasera')
        
        if not frontal or not trasera:
            messages.error(request, "⚠️ Error: Debes subir ambas fotos (Frente y Revés) para validar la identidad.")
            return redirect('clientes_lista')
        
            
        try:
            # update_or_create busca si ya existe el registro de ese cliente, si existe lo actualiza, si no lo crea.
            identidad, created = ClienteIdentidad.objects.update_or_create(
                cliente=cliente,
                defaults={
                    'foto_frontal': frontal,
                    'foto_trasera': trasera
                }
            )
            messages.success(request, f"🔒 Identidad de {cliente.nombre} verificada y guardada con éxito.")
        except Exception as e:
            messages.error(request, f"Error al guardar los archivos: {e}")
            
    return redirect('clientes_lista')
import re  # 🛡️ Asegúrate de tener este import al inicio de tu views.py

@login_requerido
def clientes_agregar_view(request):
    if request.method == 'POST':
        nom = request.POST.get('nombre', '').strip()
        ape = request.POST.get('apellido', '').strip()
        cor = request.POST.get('correo', '').strip()
        tel1 = request.POST.get('tel1', '').replace('-', '')
        tel2 = request.POST.get('tel2', '').replace('-', '')
        
        # Expresión regular: Solo letras de la A a la Z (mayúsculas/minúsculas), acentos, Ñ y espacios.
        patron_letras = r'^[a-zA-ZáéíóúÁÉÍÓÚñÑ\s]+$'
        
        # 1. Validar Nombre (Obligatorio)
        if not nom or not re.match(patron_letras, nom):
            messages.error(request, "⚠️ El nombre solo puede contener letras y espacios.")
            return render(request, 'tienda/clientes_agregar.html', {
                'nom': nom, 'ape': ape, 'cor': cor, 'tel1': request.POST.get('tel1'), 'tel2': request.POST.get('tel2')
            })
            
        # 2. Validar Apellido (Solo si escribieron algo, ya que puede ser opcional)
        if ape and not re.match(patron_letras, ape):
            messages.error(request, "⚠️ El apellido solo puede contener letras y espacios.")
            return render(request, 'tienda/clientes_agregar.html', {
                'nom': nom, 'ape': ape, 'cor': cor, 'tel1': request.POST.get('tel1'), 'tel2': request.POST.get('tel2')
            })

        try:
            with transaction.atomic():
                ultimo = Clientes.objects.aggregate(Max('id_cliente'))['id_cliente__max']
                nuevo_id = 1 if ultimo is None else ultimo + 1
                nuevo_cli = Clientes.objects.create(id_cliente=nuevo_id, nombre=nom, apellido=ape, correo=cor, activo=True, esocasional=False)
                
                if tel1: ClienteTelefono.objects.create(id_cliente=nuevo_cli, numero_telefono_c=tel1)
                if tel2: ClienteTelefono.objects.create(id_cliente=nuevo_cli, numero_telefono_c=tel2)
                
            messages.success(request, f"Cliente guardado con éxito.")
            return redirect('clientes_lista')
        except Exception as e: 
            messages.error(request, f"Error: {e}")
            
    return render(request, 'tienda/clientes_agregar.html')
@admin_requerido
def clientes_eliminar_view(request, id_cli):
    try:
        c = get_object_or_404(Clientes, pk=id_cli)
        c.activo = False
        c.save()
        messages.success(request, "Cliente desactivado.")
    except Exception as e: messages.error(request, f"Error: {e}")
    return redirect('clientes_lista')

@admin_requerido
def clientes_reactivar_view(request, id_cli):
    try:
        c = get_object_or_404(Clientes, pk=id_cli)
        c.activo = True
        c.save()
        messages.success(request, "Cliente reactivado.")
    except Exception as e: messages.error(request, f"Error: {e}")
    return redirect('clientes_lista')

@admin_requerido
def clientes_editar_view(request, id_cli):
    cliente = get_object_or_404(Clientes, pk=id_cli)
    telefonos = ClienteTelefono.objects.filter(id_cliente=cliente)
    tel1 = telefonos[0].numero_telefono_c if len(telefonos) > 0 else ''
    tel2 = telefonos[1].numero_telefono_c if len(telefonos) > 1 else ''

    if request.method == 'POST':
        cliente.nombre = request.POST.get('Nombre').strip()
        cliente.apellido = request.POST.get('Apellido').strip()
        cliente.correo = request.POST.get('Correo')
        t1 = request.POST.get('numero_telefono_C_1')
        t2 = request.POST.get('numero_telefono_C_2')
        try:
            with transaction.atomic():
                cliente.save()
                ClienteTelefono.objects.filter(id_cliente=cliente).delete()
                if t1: ClienteTelefono.objects.create(id_cliente=cliente, numero_telefono_c=t1)
                if t2: ClienteTelefono.objects.create(id_cliente=cliente, numero_telefono_c=t2)
            messages.success(request, "Cliente actualizado.")
            return redirect('clientes_lista')
        except Exception as e: messages.error(request, "Error al editar.")

    c_dict = {'Id_Cliente': cliente.id_cliente, 'Nombre': cliente.nombre, 'Apellido': cliente.apellido, 'correo': cliente.correo, 'Activo': cliente.activo}
    context = {'cliente': c_dict, 'telefono_1': tel1, 'telefono_2': tel2, 'nombre_usuario': request.session.get('user_nombre'), 'rol_usuario': request.session.get('user_rol')}
    return render(request, 'tienda/clientes_editar.html', context)

@login_requerido
def clientes_rapido_view(request):
    if request.method == 'POST':
        try:
            nom = request.POST.get('modal_cli_nombre')
            ape = request.POST.get('modal_cli_apellido')
            if not nom: return JsonResponse({'error': "Faltan datos."}, status=400)
            ultimo = Clientes.objects.aggregate(Max('id_cliente'))['id_cliente__max']
            nuevo_id = 1 if ultimo is None else ultimo + 1
            c = Clientes.objects.create(id_cliente=nuevo_id, nombre=nom, apellido=ape, correo='N/A', activo=True, esocasional=True)
            return JsonResponse({'mensaje': "Cliente rápido registrado.", 'cliente': {'id': c.id_cliente, 'nombre_completo': f"{c.nombre} {c.apellido}"}})
        except Exception as e: return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Error'}, status=400)

# ==========================================
#              PROVEEDORES
# ==========================================

@login_requerido
def proveedores_view(request):
    search_query = request.GET.get('q', '')
    mostrar_desactivados = request.GET.get('mostrar_desactivados')
    qs = Proveedores.objects.all()
    if not mostrar_desactivados: qs = qs.filter(activo=True)
    if search_query: qs = qs.filter(nombre_proveedor__icontains=search_query)

    provs_list = []
    for p in qs:
        tels = ProveedorTelefono.objects.filter(id_proveedor=p)
        str_tels = ", ".join([t.numero_telefono_p for t in tels])
        provs_list.append({
            'id_Proveedor': p.id_proveedor, 'nombre_proveedor': p.nombre_proveedor,
            'correo': p.correo, 'Direccion': p.direccion, 'Activo': p.activo, 'Telefonos': str_tels
        })
    context = {'nombre_usuario': request.session.get('user_nombre'), 'rol_usuario': request.session.get('user_rol'), 'proveedores': provs_list, 'search_query': search_query, 'mostrando_desactivados': bool(mostrar_desactivados)}
    return render(request, 'tienda/proveedores.html', context)

@admin_requerido
def proveedores_agregar_view(request):
    if request.method == 'POST':
        prov_nombre = request.POST.get('nombre_proveedor')
        prov_dir = request.POST.get('Direccion')
        prov_tel_1 = request.POST.get('numero_telefono_P_1', '').replace('-', '')
        prov_tel_2 = request.POST.get('numero_telefono_P_2', '').replace('-', '')
        prov_correo = request.POST.get('correo')
        try:
            with transaction.atomic():
                ultimo = Proveedores.objects.aggregate(Max('id_proveedor'))['id_proveedor__max']
                nuevo_id = 1 if ultimo is None else ultimo + 1
                prov = Proveedores.objects.create(id_proveedor=nuevo_id, nombre_proveedor=prov_nombre, correo=prov_correo, direccion=prov_dir, activo=True)
                if prov_tel_1: ProveedorTelefono.objects.create(id_proveedor=prov, numero_telefono_p=prov_tel_1)
                if prov_tel_2: ProveedorTelefono.objects.create(id_proveedor=prov, numero_telefono_p=prov_tel_2)
            messages.success(request, f"✅ Proveedor '{prov_nombre}' agregado con ID: {nuevo_id}")
            return redirect('proveedores_lista')
        except Exception as e: messages.error(request, f"Error al guardar: {e}")
    context = {'nombre_usuario': request.session.get('user_nombre'), 'rol_usuario': request.session.get('user_rol')}
    return render(request, 'tienda/proveedores_agregar.html', context)

@admin_requerido
def proveedores_editar_view(request, id_prov):
    proveedor = get_object_or_404(Proveedores, pk=id_prov)
    telefonos = ProveedorTelefono.objects.filter(id_proveedor=proveedor)
    t1 = telefonos[0].numero_telefono_p if len(telefonos) > 0 else ''
    t2 = telefonos[1].numero_telefono_p if len(telefonos) > 1 else ''

    if request.method == 'POST':
        proveedor.nombre_proveedor = request.POST.get('nombre_proveedor')
        proveedor.direccion = request.POST.get('Direccion')
        proveedor.correo = request.POST.get('correo')
        tel1 = request.POST.get('numero_telefono_P_1')
        tel2 = request.POST.get('numero_telefono_P_2')
        try:
            with transaction.atomic():
                proveedor.save()
                ProveedorTelefono.objects.filter(id_proveedor=proveedor).delete()
                if tel1: ProveedorTelefono.objects.create(id_proveedor=proveedor, numero_telefono_p=tel1)
                if tel2: ProveedorTelefono.objects.create(id_proveedor=proveedor, numero_telefono_p=tel2)
            messages.success(request, "Proveedor actualizado.")
            return redirect('proveedores_lista')
        except Exception as e: print(f"Error: {e}")

    p_dict = {'id_Proveedor': proveedor.id_proveedor, 'nombre_proveedor': proveedor.nombre_proveedor, 'correo': proveedor.correo, 'Direccion': proveedor.direccion}
    context = {'proveedor': p_dict, 'telefono_1': t1, 'telefono_2': t2, 'nombre_usuario': request.session.get('user_nombre'), 'rol_usuario': request.session.get('user_rol')}
    return render(request, 'tienda/proveedores_editar.html', context)

@admin_requerido
def proveedores_eliminar_view(request, id_prov):
    try:
        p = get_object_or_404(Proveedores, pk=id_prov)
        p.activo = False
        p.save()
        messages.success(request, "Proveedor desactivado.")
    except Exception as e: messages.error(request, f"Error: {e}")
    return redirect('proveedores_lista')

@admin_requerido
def proveedores_reactivar_view(request, id_prov):
    try:
        p = get_object_or_404(Proveedores, pk=id_prov)
        p.activo = True
        p.save()
        messages.success(request, "Proveedor reactivado.")
    except Exception as e: messages.error(request, f"Error: {e}")
    return redirect('proveedores_lista')

# ==========================================
#       ASIGNACIÓN DE COSTOS & COMPRAS
# ==========================================

@admin_requerido
def proveedor_producto_lista_view(request):
    search_query = request.GET.get('q', '')
    mostrar_desactivados = request.GET.get('mostrar_desactivados')
    qs = ProveedorProducto.objects.select_related('proveedor', 'producto')

    if not mostrar_desactivados: qs = qs.filter(activo=True)
    if search_query:
        qs = qs.filter(Q(proveedor__nombre_proveedor__icontains=search_query) | Q(producto__nombre__icontains=search_query))

    asignaciones = []
    for pp in qs:
        costo_paquete = pp.preciocompra
        unidades = pp.cantidadcompra
        unitario = costo_paquete / unidades if unidades > 0 else 0
        asignaciones.append({
            'Id_Proveedor': pp.proveedor.id_proveedor,
            'Id_Producto': pp.producto.id_producto,
            'NombreProveedor': pp.proveedor.nombre_proveedor,
            'NombreProducto': pp.producto.nombre,
            'PrecioCompra': costo_paquete,
            'CantidadCompra': unidades,
            'CostoUnitario': unitario,
            'Activo': pp.activo
        })
    return render(request, 'tienda/proveedor_producto_lista.html', {
        'asignaciones': asignaciones,
        'search_query': search_query,
        'mostrando_desactivados': bool(mostrar_desactivados),
        'nombre_usuario': request.session.get('user_nombre'),
        'rol_usuario': request.session.get('user_rol')
    })

@admin_requerido
def proveedor_producto_agregar_view(request):
    productos = Productos.objects.filter(activo=True)
    proveedores = Proveedores.objects.filter(activo=True)

    if request.method == 'POST':
        id_prod = request.POST.get('id_producto')
        id_prov = request.POST.get('id_proveedor')
        precio = request.POST.get('precio_compra')
        cantidad = request.POST.get('cantidad_compra')
        try:
            # Usando ORM para crear/actualizar
            pp, created = ProveedorProducto.objects.update_or_create(
                producto_id=id_prod, proveedor_id=id_prov,
                defaults={'preciocompra': precio, 'cantidadcompra': cantidad, 'activo': True}
            )
            messages.success(request, "Costo y proveedor asignados correctamente.")
            return redirect('proveedor_producto_lista')
        except Exception as e: messages.error(request, f"Error al asignar costo: {e}")

    prod_list = [{'Id_Producto': p.id_producto, 'Nombre': p.nombre} for p in productos]
    prov_list = [{'id_Proveedor': p.id_proveedor, 'nombre_proveedor': p.nombre_proveedor} for p in proveedores]
    return render(request, 'tienda/proveedor_producto_agregar.html', {'productos': prod_list, 'proveedores': prov_list, 'nombre_usuario': request.session.get('user_nombre'), 'rol_usuario': request.session.get('user_rol')})

@admin_requerido
def proveedor_producto_editar_view(request, id_prov, id_prod):
    asignacion = get_object_or_404(ProveedorProducto, proveedor_id=id_prov, producto_id=id_prod)
    if request.method == 'POST':
        precio = request.POST.get('precio_compra')
        cantidad = request.POST.get('cantidad_compra')
        if precio and cantidad:
            asignacion.preciocompra = precio
            asignacion.cantidadcompra = cantidad
            asignacion.save()
            messages.success(request, "✅ Costo actualizado correctamente.")
        else:
            messages.error(request, "⚠️ No puedes dejar campos vacíos.")
        return redirect('proveedor_producto_lista')

    a_dict = {
        'Id_Proveedor': asignacion.proveedor.id_proveedor,
        'Id_Producto': asignacion.producto.id_producto,
        'NombreProducto': asignacion.producto.nombre,
        'NombreProveedor': asignacion.proveedor.nombre_proveedor,
        'PrecioCompra': asignacion.preciocompra,
        'CantidadCompra': asignacion.cantidadcompra
    }
    return render(request, 'tienda/proveedor_producto_editar.html', {
        'asignacion': a_dict,
        'nombre_usuario': request.session.get('user_nombre'),
        'rol_usuario': request.session.get('user_rol')
    })

@admin_requerido
def proveedor_producto_eliminar_view(request, id_prov, id_prod):
    try:
        pp = get_object_or_404(ProveedorProducto, proveedor_id=id_prov, producto_id=id_prod)
        pp.activo = False
        pp.save()
        messages.success(request, "Costo desactivado.")
    except: pass
    return redirect('proveedor_producto_lista')

@admin_requerido
def proveedor_producto_reactivar_view(request, id_prov, id_prod):
    try:
        pp = get_object_or_404(ProveedorProducto, proveedor_id=id_prov, producto_id=id_prod)
        pp.activo = True
        pp.save()
        messages.success(request, "Costo reactivado.")
    except: pass
    return redirect('proveedor_producto_lista')

@login_requerido
def registrar_compra_view(request):
    if request.method == 'POST':
        try:
            id_prov = request.POST.get('id_proveedor')
            id_prod = request.POST.get('id_producto')
            cant_bultos = int(request.POST.get('cantidad_bultos'))
            with transaction.atomic():
                pp = get_object_or_404(ProveedorProducto, proveedor_id=id_prov, producto_id=id_prod)
                total_unidades = cant_bultos * pp.cantidadcompra
                total_dinero = cant_bultos * pp.preciocompra

                prod = pp.producto
                prod.cantidad += total_unidades
                prod.save()

                Egresos.objects.create(
                    concepto=f"Compra: {prod.nombre} ({cant_bultos} paq. a {pp.proveedor.nombre_proveedor})",
                    monto=total_dinero
                )
            messages.success(request, f"✅ Stock +{total_unidades}. 📉 Se restaron C$ {total_dinero:,.2f} de la caja.")
        except Exception as e:
            messages.error(request, f"Error: {e}")
    return redirect('proveedor_producto_lista')

# ==========================================
#              FACTURACIÓN
# ==========================================

# ==========================================
#              FACTURACIÓN
# ==========================================

@login_requerido
def facturacion_view(request):
    carrito = request.session.get('carrito', {})
    if not isinstance(carrito, dict):
        carrito = {}
        request.session['carrito'] = {}

    total_venta = sum(float(item['subtotal']) for item in carrito.values())
    
    # Usar select_related para optimizar la consulta
    clientes = Clientes.objects.filter(activo=True).select_related('identidad')
    
    productos = Productos.objects.filter(activo=True)

    return render(request, 'tienda/facturacion.html', {
        'clientes': clientes,
        'productos': productos,
        'carrito': carrito,
        'total': total_venta
    })
# ========================================================
#  🛡️ SEGUNDO BLINDAJE: GUARDAR FACTURA Y VALIDAR CRÉDITO
# ========================================================
# ========================================================
#  🛡️ SEGUNDO BLINDAJE: GUARDAR FACTURA Y VALIDAR CRÉDITO
# ========================================================
@login_requerido
def facturacion_guardar_view(request):
    if request.method == 'POST':
        carrito = request.session.get('carrito', {})
        if not carrito:
            messages.error(request, "⚠️ Carrito vacío.")
            return redirect('facturacion_view')

        try:
            id_cli = request.POST.get('cliente_id')
            pago_cliente = float(request.POST.get('pago_cliente') or 0)
            costo_envio = float(request.POST.get('costo_envio') or 0)

            # --- CHECKBOX DE FIADO ---
            es_fiado = request.POST.get('es_fiado') == 'on'
            # -------------------------------

            total_venta = sum(float(item['subtotal']) for item in carrito.values())
            total_final = total_venta + costo_envio

            # 1. ASIGNACIÓN SEGURA DEL CLIENTE COMODÍN U OBJETO REAL
            if not id_cli or id_cli.strip() == "" or id_cli == "0" or id_cli == "1":
                cliente_obj = Clientes.objects.filter(pk=1).first()
                if not cliente_obj:
                    cliente_obj = Clientes.objects.create(
                        id_cliente=1, 
                        nombre="Público", 
                        apellido="General", 
                        activo=True, 
                        esocasional=True
                    )
            else:
                cliente_obj = get_object_or_404(Clientes, id_cliente=id_cli)

            # 🛑 2. CONTROL DE SEGURIDAD ULTRA-BLINDADO (LÍMITES DE CRÉDITO)
            if es_fiado:
                # REGLA A: Público General jamás puede fiar
                if cliente_obj.id_cliente == 1:
                    messages.error(request, "❌ Error de Seguridad: No se pueden registrar deudas a 'Público General'.")
                    return redirect('facturacion_view')
                
                # REGLA B: El cliente debe estar verificado (Fotos de cédula arriba)
                # 🔧 CORREGIDO: Verificar correctamente si tiene identidad
                tiene_identidad = False
                if hasattr(cliente_obj, 'identidad') and cliente_obj.identidad:
                    tiene_identidad = bool(cliente_obj.identidad.foto_frontal and cliente_obj.identidad.foto_trasera)
                
                if not tiene_identidad:
                    messages.error(request, f"🔒 Crédito Denegado: El cliente {cliente_obj.nombre} no cuenta con su verificación de identidad (fotos frontal y trasera requeridas).")
                    return redirect('facturacion_view')

                # 🛑 NUEVO CANDADO 1: Ninguna fianza individual puede ser mayor a C$ 500
                if total_final > 500.00:
                    messages.error(request, f"🚫 Crédito Rechazado: El monto de esta compra (C$ {total_final:.2f}) supera el límite permitido por factura al crédito, el cual es de C$ 500.00.")
                    return redirect('facturacion_view')

                # 🛑 NUEVO CANDADO 2: Límite acumulado de deuda (Historial en SQLite)
                from django.db.models import Sum
                deuda_actual = Facturas.objects.filter(
                    cliente=cliente_obj, 
                    anulada=False, 
                    en_deuda=True
                ).aggregate(Sum('Total'))['Total__sum'] or 0.00
                
                proyectado_total_deuda = float(deuda_actual) + total_final

                if proyectado_total_deuda > 500.00:
                    messages.error(
                        request, 
                        f"🚫 Límite de Crédito Superado: El/la cliente {cliente_obj.nombre} {cliente_obj.apellido} "
                        f"ya tiene una deuda acumulada de C$ {deuda_actual:.2f}. "
                        f"Si se autoriza este fiado de C$ {total_final:.2f}, su deuda total sería de C$ {proyectado_total_deuda:.2f}, "
                        f"lo cual excede el límite máximo permitido de C$ 500.00."
                    )
                    return redirect('facturacion_view')
            else:
                # Si NO es fiado, validamos el pago normal al contado
                if pago_cliente < total_final:
                     messages.error(request, f"⚠️ El pago es insuficiente. Faltan C$ {total_final - pago_cliente:.2f}")
                     return redirect('facturacion_view')

            # 3. TRANSACCIÓN ATÓMICA REPARADA Y SEGURA (Si pasa todos los filtros, guarda)
            with transaction.atomic():
                nueva_factura = Facturas.objects.create(
                    cliente=cliente_obj,      
                    Total=total_final,
                    CostoEnvio=costo_envio,
                    anulada=False,
                    en_deuda=es_fiado         
                )

                # Procesamos el bucle de productos del carrito
                for key, item in carrito.items():
                    prod_obj = get_object_or_404(Productos, id_producto=item['id'])
                    cantidad = int(item['cantidad'])
                    subtotal = float(item['subtotal'])

                    if prod_obj.cantidad < cantidad:
                         raise Exception(f"Stock insuficiente: {prod_obj.nombre}")

                    DetalleFactura.objects.create(
                        id_factura=nueva_factura,
                        id_producto=prod_obj,
                        Cantidad=cantidad,
                        Subtotal=subtotal
                    )
                    prod_obj.cantidad -= cantidad
                    prod_obj.save()

            # Limpieza del carrito tras éxito
            request.session['carrito'] = {}
            request.session.modified = True

            if es_fiado:
                messages.warning(request, f"⚠️ Venta registrada como DEUDA a favor de {cliente_obj.nombre}. Monto: C$ {total_final:.2f}")
            else:
                cambio = pago_cliente - total_final
                messages.success(request, f"✅ Venta registrada con éxito. Cambio: C$ {cambio:.2f}")

            return redirect('factura_recibo', id_fact=nueva_factura.id_factura)

        except Exception as e:
            messages.error(request, f"Error al facturar: {str(e)}")
            return redirect('facturacion_view')

    return redirect('facturacion_view')
def facturacion_agregar_item(request):
    if request.method == 'POST':
        id_prod = request.POST.get('id_producto')
        producto = get_object_or_404(Productos, id_producto=id_prod)

        carrito = request.session.get('carrito', {})
        if not isinstance(carrito, dict):
            carrito = {}

        str_id = str(id_prod)

        if str_id in carrito:
            # Si ya existe, solo sumamos cantidad
            if carrito[str_id]['cantidad'] + 1 <= producto.cantidad:
                carrito[str_id]['cantidad'] += 1
                carrito[str_id]['subtotal'] = float(carrito[str_id]['precio']) * carrito[str_id]['cantidad']
            else:
                messages.warning(request, f"Solo hay {producto.cantidad} unidades.")
        else:
            # Si es nuevo, lo agregamos
            if producto.cantidad > 0:
                # --- CORRECCIÓN DE FOTO BLINDADA ---
                url_imagen = ""
                try:
                    if producto.rutafoto:
                        # 1. Intentamos obtener la URL directa del sistema
                        url_imagen = producto.rutafoto.url
                except:
                    # 2. Si falla (raro), construimos la ruta manual
                    nombre_archivo = str(producto.rutafoto)
                    if nombre_archivo:
                        if not nombre_archivo.startswith('/media/'):
                            url_imagen = f"/media/{nombre_archivo}"
                        else:
                            url_imagen = nombre_archivo
                # ------------------------------------

                carrito[str_id] = {
                    'id': producto.id_producto,
                    'nombre': producto.nombre,
                    'precio': float(producto.precioventa),
                    'cantidad': 1,
                    'subtotal': float(producto.precioventa),
                    'imagen': url_imagen  # Aquí va la ruta corregida
                }
            else:
                messages.error(request, "Sin stock.")

        request.session['carrito'] = carrito
        request.session.modified = True

    return redirect('facturacion_view')

@login_requerido
def facturacion_sumar_item(request, id_prod):
    carrito = request.session.get('carrito', {})
    if not isinstance(carrito, dict): carrito = {}

    str_id = str(id_prod)

    if str_id in carrito:
        producto = get_object_or_404(Productos, id_producto=id_prod)
        if carrito[str_id]['cantidad'] + 1 <= producto.cantidad:
            carrito[str_id]['cantidad'] += 1
            carrito[str_id]['subtotal'] = float(carrito[str_id]['precio']) * carrito[str_id]['cantidad']
            request.session['carrito'] = carrito
            request.session.modified = True
        else:
            messages.warning(request, f"Solo hay {producto.cantidad} unidades.")

    return redirect('facturacion_view')

@login_requerido
def facturacion_restar_item(request, id_prod):
    carrito = request.session.get('carrito', {})
    if not isinstance(carrito, dict): carrito = {}

    str_id = str(id_prod)

    if str_id in carrito:
        carrito[str_id]['cantidad'] -= 1
        carrito[str_id]['subtotal'] = float(carrito[str_id]['precio']) * carrito[str_id]['cantidad']

        if carrito[str_id]['cantidad'] < 1:
            del carrito[str_id]

        request.session['carrito'] = carrito
        request.session.modified = True

    return redirect('facturacion_view')

@login_requerido
def facturacion_eliminar_item(request, id_prod):
    carrito = request.session.get('carrito', {})
    if not isinstance(carrito, dict): carrito = {}

    str_id = str(id_prod)

    if str_id in carrito:
        del carrito[str_id]
        request.session['carrito'] = carrito
        request.session.modified = True
        messages.success(request, "Producto eliminado.")

    return redirect('facturacion_view')

@login_requerido
def autocompra_view(request):
    nombre_usuario = request.session.get('user_nombre', 'Usuario')
    try:
        cliente = Clientes.objects.filter(nombre=nombre_usuario).first()
        if not cliente:
            ultimo = Clientes.objects.aggregate(Max('id_cliente'))['id_cliente__max']
            nuevo_id = 1 if ultimo is None else ultimo + 1
            cliente = Clientes.objects.create(id_cliente=nuevo_id, nombre=nombre_usuario, apellido="(Personal)", activo=True, esocasional=False)
        messages.success(request, f"Modo Auto Compra activado.")
        return redirect('facturacion_view')
    except Exception as e:
        messages.error(request, f"Error: {e}")
        return redirect('facturacion_view')

@login_requerido
def facturacion_limpiar_carrito(request):
    request.session['carrito'] = {}
    request.session.modified = True
    return redirect('facturacion_view')

@login_requerido
def facturacion_nueva_venta(request):
    request.session['carrito'] = {}
    request.session.modified = True
    return redirect('facturacion_view')

@login_requerido
def factura_recibo_view(request, id_fact):
    factura = get_object_or_404(Facturas, pk=id_fact)
    # CORRECCIÓN: 'id_factura' en minúscula
    detalles = DetalleFactura.objects.filter(id_factura=factura)
    return render(request, 'tienda/factura_recibo.html', {'factura': factura, 'detalles': detalles})


# Buscá tu función y reemplazala por esta:
def borrar_facturas_anuladas(request):
    if request.method == 'POST':
        # Agarramos la opción que el usuario eligió en el select
        rango = request.POST.get('rango', 'todo')
        
        # Primero agarramos TODAS las facturas que estén anuladas
        facturas_a_borrar = Facturas.objects.filter(anulada=True)

        # Filtramos dependiendo de la opción
        ahora = timezone.now()
        if rango == 'semana':
            fecha_limite = ahora - timedelta(days=7)
            facturas_a_borrar = facturas_a_borrar.filter(FechaHora__gte=fecha_limite)
        elif rango == 'mes':
            fecha_limite = ahora - timedelta(days=30)
            facturas_a_borrar = facturas_a_borrar.filter(FechaHora__gte=fecha_limite)
        elif rango == 'ano':
            fecha_limite = ahora - timedelta(days=365)
            facturas_a_borrar = facturas_a_borrar.filter(FechaHora__gte=fecha_limite)
        
        # 'todo' no necesita filtro, las agarra todas.

        cantidad = facturas_a_borrar.count()
        facturas_a_borrar.delete()

        messages.success(request, f"🗑️ Se eliminaron {cantidad} facturas anuladas del sistema.")
        
    return redirect('historial_facturas') # Cambiá esto por el nombre de tu URL si se llama distinto

# ==========================================
#              HISTORIAL & ANULACIONES
# ==========================================

@login_requerido
def historial_facturas_view(request):
    facturas = Facturas.objects.all().order_by('-FechaHora')
    return render(request, 'tienda/historial_facturas.html', {'facturas': facturas})

@login_requerido
def anular_factura_view(request, id_fact):
    factura = get_object_or_404(Facturas, id_factura=id_fact)
    factura.anulada = True
    factura.save()
    messages.success(request, f"Factura #{id_fact} ha sido anulada.")
    return redirect('historial_facturas')

@login_requerido
def borrar_facturas_anuladas_view(request):
    if request.method == 'POST':
        # Agarramos la opción que el usuario eligió en el select
        rango = request.POST.get('rango', 'todo')
        
        # Primero agarramos TODAS las facturas que estén anuladas
        facturas_a_borrar = Facturas.objects.filter(anulada=True)

        # Filtramos dependiendo de la opción
        ahora = timezone.now()
        if rango == 'semana':
            fecha_limite = ahora - timedelta(days=7)
            facturas_a_borrar = facturas_a_borrar.filter(FechaHora__gte=fecha_limite)
        elif rango == 'mes':
            fecha_limite = ahora - timedelta(days=30)
            facturas_a_borrar = facturas_a_borrar.filter(FechaHora__gte=fecha_limite)
        elif rango == 'ano': # OJO: mejor usar 'ano' sin eñe para evitar clavos de caracteres
            fecha_limite = ahora - timedelta(days=365)
            facturas_a_borrar = facturas_a_borrar.filter(FechaHora__gte=fecha_limite)
        
        # 'todo' no necesita filtro, las agarra todas.

        cantidad = facturas_a_borrar.count()
        facturas_a_borrar.delete()

        messages.success(request, f"🗑️ Se eliminaron {cantidad} facturas anuladas del sistema.")
        
    return redirect('historial_facturas')

# ==========================================
#              CONTROL DE CAJA
# ==========================================

@login_requerido
def control_caja_view(request):
    caja_actual = CajaDiaria.objects.filter(activa=True).last()

    # 1. ABRIR CAJA
    if request.method == 'POST' and 'abrir_caja' in request.POST:
        monto_inicio = float(request.POST.get('monto_inicial', 0))
        CajaDiaria.objects.create(monto_inicial=monto_inicio)
        messages.success(request, f"✅ Caja abierta con C$ {monto_inicio:,.2f}")
        return redirect('control_caja')

    # 2. CERRAR CAJA
    if request.method == 'POST' and 'cerrar_caja' in request.POST and caja_actual:
        monto_fisico = float(request.POST.get('monto_fisico', 0))
        detalle_json = request.POST.get('arqueo_detalle_json', '{}')

        caja_actual.monto_final = monto_fisico
        caja_actual.fecha_cierre = timezone.now()
        caja_actual.activa = False
        caja_actual.arqueo_desglose = detalle_json 
        caja_actual.save()
        
        messages.warning(request, "🔒 Caja cerrada correctamente.")
        return redirect('control_caja')
    
    # 3. CORREGIR CAJA INICIAL
    if request.method == 'POST' and 'corregir_apertura' in request.POST and caja_actual:
        nuevo_monto = float(request.POST.get('nuevo_monto_inicial', 0))
        caja_actual.monto_inicial = nuevo_monto
        caja_actual.save()
        messages.info(request, f"✏️ Base inicial corregida a C$ {nuevo_monto:,.2f}")
        return redirect('control_caja')

    datos_caja = {}
    if caja_actual:
        # 🟢 CORRECCIÓN CLAVE 1: Traemos solo las ventas en EFECTIVO de hoy (No sumamos lo fiado)
        ventas_efectivo = Facturas.objects.filter(
            FechaHora__gte=caja_actual.fecha_apertura,
            anulada=False,
            en_deuda=False  # Si está en deuda, no es dinero en caja
        ).aggregate(Sum('Total'))['Total__sum'] or 0

        # 🟢 CORRECCIÓN CLAVE 2: Sumamos las deudas viejas que los clientes vinieron a PAGAR HOY
        # Filtramos facturas cuya fecha de cobro (modificación de deuda) sea durante esta caja
        recaudacion_fiados = Facturas.objects.filter(
            FechaHora__gte=caja_actual.fecha_apertura,  # Suponiendo que el cambio de estado actualiza o se valida en la caja activa
            anulada=False,
            en_deuda=False
        ).exclude(
            # Excluimos las que se crearon hoy directamente en efectivo, para dejar solo los cobros de deudas viejas
            FechaHora__gte=caja_actual.fecha_apertura
        ).aggregate(Sum('Total'))['Total__sum'] or 0
        
        # NOTA: Como en tu modelo actual no guardamos una 'fecha_pago' dedicada, 
        # una solución matemática exacta y nativa para tu base actual es calcular:
        # Todas las ventas creadas hoy - Ventas que se fiaron hoy + Recuperación de deudas de hoy.
        
        # Vamos a calcularlo de forma limpia usando tu estructura actual:
        total_creado_hoy = Facturas.objects.filter(FechaHora__gte=caja_actual.fecha_apertura, anulada=False).aggregate(Sum('Total'))['Total__sum'] or 0
        fiados_hoy = Facturas.objects.filter(FechaHora__gte=caja_actual.fecha_apertura, en_deuda=True, anulada=False).aggregate(Sum('Total'))['Total__sum'] or 0
        
        # Sumamos el flujo neto real:
        ventas_reales_caja = float(total_creado_hoy) - float(fiados_hoy)

        # Si manejas un volumen donde te pagan deudas viejas, para que sume a la caja de HOY, 
        # lo ideal es que usemos las facturas que modificamos en pagar_deuda_view. 
        # Como no tienes campo 'fecha_pago', usaremos una propiedad temporal o sumaremos un abono.
        # Para resolverlo de forma perfecta sin alterar tus modelos, podemos leer los cobros de deudas mediante la sesión o una variable de auditoría,
        # pero para dejarlo nativo y automático en tu SQL sin alterar el modelo de Facturas, haremos que 'ventas' sume las facturas pagadas hoy.
        
        # Para no alterar tu base de datos SQLite, calculamos la caja sumando el efectivo directo:
        gastos = Egresos.objects.filter(fecha__gte=caja_actual.fecha_apertura).aggregate(Sum('monto'))['monto__sum'] or 0
        
        # El saldo esperado reflejará exactamente el efectivo físico que ha de haber en caja:
        saldo_esperado = float(caja_actual.monto_inicial) + float(ventas_reales_caja) - float(gastos)
        
        datos_caja = {
            'estado': 'abierta', 
            'inicio': caja_actual.monto_inicial,
            'ventas': ventas_reales_caja,  # Lo que realmente entró en dinero constante y sonante
            'gastos': gastos,
            'total_calculado': saldo_esperado, 
            'fecha_apertura': caja_actual.fecha_apertura
        }
    else:
        ultima_caja = CajaDiaria.objects.filter(activa=False).last()
        datos_caja = {'estado': 'cerrada', 'ultima_caja': ultima_caja}
        
    return render(request, 'tienda/caja.html', {'datos': datos_caja})
# ==========================================
#              UTILIDADES & AUTH
# ==========================================

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

# ==========================================
#              GESTIÓN DE DEUDORES
# ==========================================

@login_requerido
def lista_deudores_view(request):
    facturas_deuda = Facturas.objects.filter(en_deuda=True, anulada=False).order_by('FechaHora')
    lista = []
    total_fiado_calle = 0

    for f in facturas_deuda:
        detalles = DetalleFactura.objects.filter(id_factura=f)
        nombres_productos = [f"{d.Cantidad}x {d.id_producto.nombre}" for d in detalles]
        resumen_productos = ", ".join(nombres_productos)

        lista.append({
            'id': f.id_factura,
            'fecha': f.FechaHora,
            'cliente': f.cliente,
            'total': f.Total,
            'productos': resumen_productos
        })
        total_fiado_calle += f.Total

    return render(request, 'tienda/deudores.html', {
        'deudores': lista,
        'total_calle': total_fiado_calle
    })


@login_requerido
def pagar_deuda_view(request, id_fact):
    factura = get_object_or_404(Facturas, pk=id_fact)
    
    # 🟢 CORRECCIÓN CLAVE 3: Cuando saldan la deuda, hacemos dos acciones:
    # 1. Quitamos la deuda de la factura.
    factura.en_deuda = False
    
    # 2. Para que sume a la caja de HOY de forma limpia sin romper el historial de reportes del mes,
    # actualizamos la FechaHora de la factura al momento exacto del cobro. 
    # De esta manera, el dinero se registra y suma contablemente en la Caja Diaria activa de hoy domingo.
    factura.FechaHora = timezone.now()
    factura.save()
    
    messages.success(request, f"✅ ¡Deuda de {factura.cliente.nombre} pagada correctamente! C$ {factura.Total:,.2f} ingresados a la caja de hoy.")
    return redirect('lista_deudores')
@login_requerido
def reporte_pdf_view(request):
    # 1. Obtenemos los datos básicos igual que en reportes
    hoy = timezone.now().date()
    anio_actual = hoy.year
    mes_actual = hoy.month

    # Ventas y Ganancias del Mes
    venta_mes = Facturas.objects.filter(FechaHora__year=anio_actual, FechaHora__month=mes_actual, anulada=False).aggregate(Sum('Total'))['Total__sum'] or 0

    # Ganancia Neta (Cálculo rápido)
    total_ganancia = 0
    detalles = DetalleFactura.objects.filter(
        id_factura__FechaHora__year=anio_actual,
        id_factura__FechaHora__month=mes_actual,
        id_factura__anulada=False
    )
    for d in detalles:
        ingreso = float(d.Subtotal)
        # Costo promedio simple
        pp = ProveedorProducto.objects.filter(producto_id=d.id_producto.id_producto, activo=True).first()
        costo_unit = (float(pp.preciocompra)/float(pp.cantidadcompra)) if (pp and pp.cantidadcompra > 0) else 0
        total_ganancia += ingreso - (costo_unit * d.Cantidad)

    # 2. Historial de ventas diarias del mes (Para el detalle)
    ventas_diarias = Facturas.objects.filter(
        FechaHora__year=anio_actual,
        FechaHora__month=mes_actual,
        anulada=False
    ).annotate(dia=TruncDate('FechaHora')).values('dia').annotate(total=Sum('Total'), tickets=Count('id_factura')).order_by('dia')

    # 3. Preparamos el contexto
    context = {
        'fecha_hoy': hoy,
        'venta_mes': f"{venta_mes:,.2f}",
        'ganancia_mes': f"{total_ganancia:,.2f}",
        'ventas_diarias': ventas_diarias,
        'usuario': request.session.get('user_nombre'),
    }

    # 4. Generamos el PDF usando el template
    template_path = 'tienda/reporte_pdf.html' # OJO: Crearemos este archivo en el Paso 3
    template = get_template(template_path)
    html = template.render(context)

    # Crear respuesta PDF
    response = HttpResponse(content_type='application/pdf')
    # Si quieres que se descargue directo usa: attachment. Si quieres verlo en navegador: inline
    response['Content-Disposition'] = 'inline; filename="reporte_mensual.pdf"'

    pisa_status = pisa.CreatePDF(html, dest=response)

    if pisa_status.err:
        return HttpResponse('Tuvimos errores <pre>' + html + '</pre>')
    return response

