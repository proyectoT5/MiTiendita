from django.db import models
from django.contrib.auth.models import User
# ==========================================
#  MODELOS "LEGACY" (Corregidos a minúsculas)
# ==========================================

class Clientes(models.Model):
    id_cliente = models.IntegerField(db_column='id_cliente', primary_key=True)
    nombre = models.CharField(db_column='nombre', max_length=100)
    apellido = models.CharField(db_column='apellido', max_length=100, blank=True, null=True)
    correo = models.CharField(db_column='correo', max_length=150, blank=True, null=True)
    activo = models.BooleanField(db_column='activo', default=True)
    esocasional = models.BooleanField(db_column='EsOcasional', default=False)

    class Meta:
        managed = True
        db_table = 'Clientes'

    def __str__(self):
        return f"{self.nombre} {self.apellido or ''}"

class ClienteTelefono(models.Model):
    id_telefonocli = models.AutoField(db_column='id_telefonoCli', primary_key=True)
    id_cliente = models.ForeignKey(Clientes, models.DO_NOTHING, db_column='id_cliente')
    numero_telefono_c = models.CharField(db_column='numero_telefono_C', max_length=20)

    class Meta:
        managed = True
        db_table = 'ClienteTelefono'

class Proveedores(models.Model):
    id_proveedor = models.IntegerField(db_column='id_Proveedor', primary_key=True)
    nombre_proveedor = models.CharField(db_column='nombre_proveedor', max_length=100)
    correo = models.CharField(db_column='correo', max_length=100, blank=True, null=True)
    direccion = models.TextField(db_column='Direccion', blank=True, null=True)
    activo = models.BooleanField(db_column='Activo', default=True)

    class Meta:
        managed = True
        db_table = 'Proveedores'

    def __str__(self):
        return self.nombre_proveedor

class ProveedorTelefono(models.Model):
    id_telefonoprove = models.AutoField(db_column='id_telefonoProve', primary_key=True)
    id_proveedor = models.ForeignKey(Proveedores, models.DO_NOTHING, db_column='id_Proveedor')
    numero_telefono_p = models.CharField(db_column='numero_telefono_P', max_length=20)

    class Meta:
        managed = True
        db_table = 'ProveedorTelefono'

class Productos(models.Model):
    # CAMBIO IMPORTANTE: id_producto en minúscula para Python, apuntando a Id_Producto en SQL
    id_producto = models.IntegerField(db_column='Id_Producto', primary_key=True)
    nombre = models.CharField(db_column='Nombre', max_length=100)
    precioventa = models.DecimalField(db_column='PrecioVenta', max_digits=10, decimal_places=2)
    cantidad = models.IntegerField(db_column='Cantidad', default=0)
    rutafoto = models.ImageField(db_column='rutaFoto', upload_to='productos/', null=True, blank=True)
    stockminimo = models.IntegerField(db_column='StockMinimo', blank=True, null=True)
    activo = models.BooleanField(db_column='Activo', default=True)
    idproveedor = models.ForeignKey(Proveedores, models.DO_NOTHING, db_column='IdProveedor', blank=True, null=True)

    class Meta:
        managed = True
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
        managed = True
        db_table = 'ProveedorProducto'

# ==========================================
#  NUEVOS MODELOS (Sistema Financiero)
# ==========================================



class Egresos(models.Model):
    fecha = models.DateTimeField(auto_now_add=True)
    concepto = models.CharField(max_length=200)
    monto = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.concepto} - C$ {self.monto}"

class CajaDiaria(models.Model):
    fecha_apertura = models.DateTimeField(auto_now_add=True)
    fecha_cierre = models.DateTimeField(null=True, blank=True)
    monto_inicial = models.DecimalField(max_digits=10, decimal_places=2)
    monto_final = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    activa = models.BooleanField(default=True)
    # NUEVO: Aquí vamos a guardar la lista de billetes en formato de texto (JSON)
    arqueo_desglose = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Caja {self.fecha_apertura}"

class Facturas(models.Model):
    id_factura = models.AutoField(primary_key=True)
    FechaHora = models.DateTimeField(auto_now_add=True)
    cliente = models.ForeignKey(Clientes, on_delete=models.CASCADE)
    Total = models.DecimalField(max_digits=10, decimal_places=2)
    CostoEnvio = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    anulada = models.BooleanField(default=False)
    en_deuda = models.BooleanField(default=False)  # True = Me debe, False = Ya pagó

    def __str__(self):
        return f"Factura #{self.id_factura}"

class DetalleFactura(models.Model):
    id_factura = models.ForeignKey(Facturas, on_delete=models.CASCADE)
    id_producto = models.ForeignKey(Productos, on_delete=models.CASCADE)
    Cantidad = models.IntegerField()
    Subtotal = models.DecimalField(max_digits=10, decimal_places=2)

class UserOTP(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    secret = models.CharField(max_length=32)

    def __str__(self):
        return f"OTP - {self.user.username}"