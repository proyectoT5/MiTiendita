from django.db import models

class Productos(models.Model):
    id_producto = models.IntegerField(db_column='Id_Producto', primary_key=True)
    nombre = models.CharField(db_column='Nombre', max_length=100, db_collation='Modern_Spanish_CI_AS', blank=True, null=True)
    precioventa = models.DecimalField(db_column='PrecioVenta', max_digits=10, decimal_places=2, blank=True, null=True)
    cantidad = models.IntegerField(db_column='Cantidad', blank=True, null=True)
    rutafoto = models.CharField(db_column='rutaFoto', max_length=500, db_collation='Modern_Spanish_CI_AS', blank=True, null=True)
    stockminimo = models.IntegerField(db_column='StockMinimo', blank=True, null=True)
    activo = models.BooleanField(db_column='Activo')
    idproveedor = models.IntegerField(db_column='IdProveedor', blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'Productos'