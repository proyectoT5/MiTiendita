from django.db import models

# ==========================================
# 1. TABLAS EXISTENTES (Managed = False)
# ==========================================

class Clientes(models.Model):
    id_cliente = models.IntegerField(db_column='id_cliente', primary_key=True)
    nombre = models.CharField(db_column='nombre', max_length=100)
    apellido = models.CharField(db_column='apellido', max_length=100, blank=True, null=True)
    
    # IMPORTANTE: Si te da error en uno de estos, es porque en tu SQL Server 
    # la columna se llama diferente (ej: 'tel', 'celular', 'dir').
    # Si no estás seguro, comenta estas líneas y deja solo id, nombre y apellido.
    telefono_principal = models.CharField(db_column='telefono', max_length=20, blank=True, null=True)
    telefono_secundario = models.CharField(db_column='telefono2', max_length=20, blank=True, null=True)
    direccion = models.TextField(db_column='direccion_cliente', blank=True, null=True)
    activo = models.BooleanField(db_column='activo', default=True)

    class Meta:
        managed = False 
        db_table = 'Clientes'

    def __str__(self):
        return f"{self.nombre} {self.apellido or ''}"


class Proveedores(models.Model):
    id_proveedor = models.AutoField(db_column='Id_Proveedor', primary_key=True)
    nombre = models.CharField(db_column='Nombre', max_length=100)
    telefono = models.CharField(db_column='Telefono', max_length=20, blank=True, null=True)
    contacto = models.CharField(db_column='Contacto', max_length=100, blank=True, null=True)
    activo = models.BooleanField(db_column='Activo', default=True)

    class Meta:
        managed = False
        db_table = 'Proveedores'
        verbose_name_plural = "Proveedores"

    def __str__(self):
        return self.nombre


class Productos(models.Model):
    # Usamos IntegerField porque tu SQL Server no es automático (Identity)
    id_producto = models.IntegerField(db_column='Id_Producto', primary_key=True)
    nombre = models.CharField(db_column='Nombre', max_length=100)
    precioventa = models.DecimalField(db_column='PrecioVenta', max_digits=10, decimal_places=2)
    cantidad = models.IntegerField(db_column='Cantidad', default=0)
    rutafoto = models.ImageField(db_column='rutaFoto', upload_to='productos/', null=True, blank=True)
    stockminimo = models.IntegerField(db_column='StockMinimo', blank=True, null=True)
    activo = models.BooleanField(db_column='Activo', default=True)
    
    # ⚠️ IMPORTANTE: El nombre del campo debe ser idproveedor para que coincida con la BD
    idproveedor = models.ForeignKey(Proveedores, models.DO_NOTHING, db_column='IdProveedor', blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'Productos'

    def __str__(self):
        return self.nombre


class ProveedorProducto(models.Model):
    id_asignacion = models.AutoField(db_column='Id_Asignacion', primary_key=True)
    proveedor = models.ForeignKey(Proveedores, models.DO_NOTHING, db_column='Id_Proveedor')
    producto = models.ForeignKey(Productos, models.DO_NOTHING, db_column='Id_Producto')
    preciocompra = models.DecimalField(db_column='PrecioCompra', max_digits=10, decimal_places=2)
    cantidadcompra = models.IntegerField(db_column='CantidadCompra', default=1)
    activo = models.BooleanField(db_column='Activo', default=True)

    class Meta:
        managed = False
        db_table = 'ProveedorProducto'
        verbose_name_plural = "Costos"


# ==========================================
# 2. TABLAS NUEVAS (Managed = True)
# ==========================================

class Facturas(models.Model):
    Id_Factura = models.IntegerField(db_column='id_factura', primary_key=True)
    Fecha = models.DateTimeField(db_column='FechaHora', auto_now_add=True)
    Cliente = models.ForeignKey(Clientes, models.DO_NOTHING, db_column='id_cliente')
    Total = models.DecimalField(db_column='Total', max_digits=10, decimal_places=2)
    # Campos extra de tu BD vieja
    MontoPagado = models.DecimalField(db_column='MontoPagado', max_digits=10, decimal_places=2, null=True, blank=True)
    Cambio = models.DecimalField(db_column='Cambio', max_digits=10, decimal_places=2, null=True, blank=True)
    CostoEnvio = models.DecimalField(db_column='CostoEnvio', max_digits=10, decimal_places=2, null=True, blank=True)

    class Meta:
        managed = False   # <--- ESTO EN FALSO (Usamos la tabla vieja 'factura')
        db_table = 'factura' 
        verbose_name_plural = "Facturas"

class DetalleFactura(models.Model):
    # Asumimos que esta tabla también existe ya. 
    # Si te da error de columnas, avísame para ajustar los nombres.
    Id_Detalle = models.AutoField(primary_key=True)
    Factura = models.ForeignKey(Facturas, models.DO_NOTHING, db_column='id_factura')
    Producto = models.ForeignKey(Productos, models.DO_NOTHING, db_column='id_producto')
    Cantidad = models.IntegerField()
    Subtotal = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        managed = False # Usamos la tabla existente
        db_table = 'DetalleFactura' # Asegúrate que este sea el nombre en SQL
        verbose_name_plural = "Detalles de Factura"