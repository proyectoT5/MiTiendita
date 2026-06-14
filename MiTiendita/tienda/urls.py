from django.urls import path
from . import views
# --- IMPORTS PARA IMÁGENES ---
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    # --- PANEL PRINCIPAL ---
    path('', views.dashboard_view, name='dashboard'),
    path('reportes/', views.reportes_view, name='reportes_view'),

    # --- FACTURACIÓN (VENTAS) ---
    path('facturacion/', views.facturacion_view, name='facturacion_view'),
    path('facturacion/nueva/', views.facturacion_nueva_venta, name='facturacion_nueva'),
    path('facturacion/agregar/', views.facturacion_agregar_item, name='facturacion_agregar_item'),

    # ✅ ESTA ES LA LÍNEA QUE DABA EL ERROR (Corregida)
    # Antes se llamaba 'facturacion_guardar', ahora 'facturacion_guardar_view'
    path('facturacion/guardar/', views.facturacion_guardar_view, name='facturacion_guardar_view'),

    path('facturacion/limpiar/', views.facturacion_limpiar_carrito, name='facturacion_limpiar_carrito'),

    # ✅ RUTAS DEL CARRITO
    path('facturacion/restar/<int:id_prod>/', views.facturacion_restar_item, name='facturacion_restar_item'),
    path('facturacion/sumar/<int:id_prod>/', views.facturacion_sumar_item, name='facturacion_sumar_item'),
    path('facturacion/eliminar/<int:id_prod>/', views.facturacion_eliminar_item, name='facturacion_eliminar_item'),

    path('facturacion/autocompra/', views.autocompra_view, name='facturacion_autocompra'),

    # ✅ TICKET Y ANULAR
    path('facturacion/recibo/<int:id_fact>/', views.factura_recibo_view, name='factura_recibo'),
    path('facturacion/anular/<int:id_fact>/', views.anular_factura_view, name='anular_factura'),

    # --- PRODUCTOS ---
    path('productos/', views.productos_view, name='productos_lista'),
    path('productos/agregar/', views.productos_agregar_view, name='productos_agregar'),
    path('productos/editar/<int:id_prod>/', views.productos_editar_view, name='productos_editar'),
    path('productos/eliminar/<int:id_prod>/', views.productos_eliminar_view, name='productos_eliminar'),
    path('productos/reactivar/<int:id_prod>/', views.productos_reactivar_view, name='productos_reactivar'),
    path('buscar-producto/', views.buscar_producto_ajx, name='buscar_producto_ajx'),
    path('productos/abastecer/<int:id_prod>/', views.productos_abastecer_view, name='productos_abastecer'),

    # --- CLIENTES ---
    path('clientes/', views.clientes_view, name='clientes_lista'),
    path('clientes/agregar/', views.clientes_agregar_view, name='clientes_agregar'),
    path('clientes/editar/<int:id_cli>/', views.clientes_editar_view, name='clientes_editar'),
    path('clientes/eliminar/<int:id_cli>/', views.clientes_eliminar_view, name='clientes_eliminar'),
    path('clientes/reactivar/<int:id_cli>/', views.clientes_reactivar_view, name='clientes_reactivar'),
    path('clientes/rapido/', views.clientes_rapido_view, name='clientes_rapido'),

    #---- ClienteIdentificaion ----
    path('clientes/cargar',views.cargar_identidad_view,name='cargar_identidad'),

    # --- PROVEEDORES ---
    path('proveedores/', views.proveedores_view, name='proveedores_lista'),
    path('proveedores/agregar/', views.proveedores_agregar_view, name='proveedores_agregar'),
    path('proveedores/editar/<int:id_prov>/', views.proveedores_editar_view, name='proveedores_editar'),
    path('proveedores/eliminar/<int:id_prov>/', views.proveedores_eliminar_view, name='proveedores_eliminar'),
    path('proveedores/reactivar/<int:id_prov>/', views.proveedores_reactivar_view, name='proveedores_reactivar'),

    # --- COSTOS ---
    path('costos/', views.proveedor_producto_lista_view, name='proveedor_producto_lista'),
    path('costos/agregar/', views.proveedor_producto_agregar_view, name='proveedor_producto_agregar'),
    path('costos/editar/<int:id_prov>/<int:id_prod>/', views.proveedor_producto_editar_view, name='proveedor_producto_editar'),
    path('costos/eliminar/<int:id_prov>/<int:id_prod>/', views.proveedor_producto_eliminar_view, name='proveedor_producto_eliminar'),
    path('costos/reactivar/<int:id_prov>/<int:id_prod>/', views.proveedor_producto_reactivar_view, name='proveedor_producto_reactivar'),
    path('costos/abastecer/', views.registrar_compra_view, name='registrar_compra'),

    # --- OTROS ---
    path('prediccion/', views.prediccion_view, name='prediccion_view'),

    path('caja/', views.control_caja_view, name='control_caja'),
    path('historial/', views.historial_facturas_view, name='historial_facturas'),
    path('historial/anular/<int:id_fact>/', views.anular_factura_view, name='anular_factura'),
    path('historial/limpiar-anuladas/', views.borrar_facturas_anuladas_view, name='borrar_facturas_anuladas'),
    path('deudores/', views.lista_deudores_view, name='lista_deudores'),
    path('deudores/pagar/<int:id_fact>/', views.pagar_deuda_view, name='pagar_deuda'),
    path('reportes/pdf/', views.reporte_pdf_view, name='reporte_pdf'),

    path('productos/guardar-borrador/', views.guardar_borrador_producto_view, name='guardar_borrador_producto'),

    

    

]

# --- MAGIA PARA FOTOS ---
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)