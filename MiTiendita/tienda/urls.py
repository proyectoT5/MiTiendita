from django.urls import path
from . import views

urlpatterns = [

   

    # Dashboard y Reportes
    path('', views.dashboard_view, name='dashboard'),
    path('reportes/', views.reportes_view, name='reportes_view'),
    
    # --- Productos ---
    path('productos/', views.productos_view, name='productos_lista'),
    path('productos/agregar/', views.productos_agregar_view, name='productos_agregar'),
    path('productos/eliminar/<int:id_prod>/', views.productos_eliminar_view, name='productos_eliminar'),
    path('productos/reactivar/<int:id_prod>/', views.productos_reactivar_view, name='productos_reactivar'),
    path('productos/editar/<int:id_prod>/', views.productos_editar_view, name='productos_editar'),
    
    # --- Clientes ---
    path('clientes/', views.clientes_view, name='clientes_lista'),
    path('clientes/agregar/', views.clientes_agregar_view, name='clientes_agregar'),
    path('clientes/eliminar/<int:id_cli>/', views.clientes_eliminar_view, name='clientes_eliminar'),
    path('clientes/reactivar/<int:id_cli>/', views.clientes_reactivar_view, name='clientes_reactivar'),
    path('clientes/editar/<int:id_cli>/', views.clientes_editar_view, name='clientes_editar'),
    path('clientes/rapido/', views.clientes_rapido_view, name='clientes_rapido'),

    # --- Proveedores ---
    path('proveedores/', views.proveedores_view, name='proveedores_lista'),
    path('proveedores/agregar/', views.proveedores_agregar_view, name='proveedores_agregar'),
    path('proveedores/eliminar/<int:id_prov>/', views.proveedores_eliminar_view, name='proveedores_eliminar'),
    path('proveedores/reactivar/<int:id_prov>/', views.proveedores_reactivar_view, name='proveedores_reactivar'),
    path('proveedores/editar/<int:id_prov>/', views.proveedores_editar_view, name='proveedores_editar'),
    
    # --- Asignaciones (Costos Proveedor-Producto) ---
    path('asignaciones/', views.proveedor_producto_lista_view, name='proveedor_producto_lista'),
    path('asignaciones/agregar/', views.proveedor_producto_agregar_view, name='proveedor_producto_agregar'),
    path('asignaciones/editar/<int:id_prov>/<int:id_prod>/', views.proveedor_producto_editar_view, name='proveedor_producto_editar'),
    path('asignaciones/eliminar/<int:id_prov>/<int:id_prod>/', views.proveedor_producto_eliminar_view, name='proveedor_producto_eliminar'),
    path('asignaciones/reactivar/<int:id_prov>/<int:id_prod>/', views.proveedor_producto_reactivar_view, name='proveedor_producto_reactivar'),

    # --- Facturación ---
    path('facturacion/', views.facturacion_view, name='facturacion_view'),
    path('facturacion/agregar/', views.facturacion_agregar_item, name='facturacion_agregar_item'),
    path('facturacion/eliminar/<int:item_index>/', views.facturacion_eliminar_item, name='facturacion_eliminar_item'),
    path('facturacion/guardar/', views.facturacion_guardar_view, name='facturacion_guardar'),
    path('facturacion/recibo/<int:id_fact>/', views.factura_recibo_view, name='factura_recibo'),
    path('facturacion/autocompra/', views.autocompra_view, name='facturacion_autocompra'),
    
    # --- Predicción ---
    path('prediccion/', views.prediccion_view, name='prediccion_view'),

    # ... (en la sección de Asignaciones) ...
    path('asignaciones/reactivar/<int:id_prov>/<int:id_prod>/', views.proveedor_producto_reactivar_view, name='proveedor_producto_reactivar'),
    
    # ¡NUEVA RUTA!
    path('asignaciones/comprar/', views.registrar_compra_view, name='registrar_compra'),

    #recuperacion de cuenta
    path('recuperar/', views.recuperar_password_view, name='recuperar_password'),
    path('cambiar-password/<str:token>/', views.cambiar_password_view, name='cambiar_password'),
    
    

]