USE django_sqlserver;

CREATE TABLE Usuarios (
    IdUsuario INT PRIMARY KEY,
    Nombre NVARCHAR(15),
    Contraseña NVARCHAR(30),
    Rol NVARCHAR(15)
);

CREATE TABLE Clientes (
    Id_Cliente INT PRIMARY KEY,
    Nombre NVARCHAR(20),
    Apellido NVARCHAR(20)
);


CREATE TABLE Proveedores (
    id_Proveedor INT PRIMARY KEY,
    nombre_proveedor NVARCHAR(50),
    correo NVARCHAR(40),
    Direccion NVARCHAR(50)
);

CREATE TABLE Productos (
    Id_Producto INT PRIMARY KEY,
    Nombre NVARCHAR(15),
    PrecioVenta DECIMAL(10, 2),
    Cantidad INT,
    rutaFoto NVARCHAR(500)
);

CREATE TABLE ProveedorProducto (
    Id_Proveedor INT,
    Id_Producto INT,
    PrecioCompra DECIMAL(10, 2), 
    
    PRIMARY KEY (Id_Proveedor, Id_Producto), 
    FOREIGN KEY (Id_Proveedor) REFERENCES Proveedores(id_Proveedor),
    FOREIGN KEY (Id_Producto) REFERENCES Productos(Id_Producto)
);

CREATE TABLE ClienteTelefono (
    id_telefonoCli INT PRIMARY KEY,
    id_cliente INT,
    numero_telefono_C NVARCHAR(10),
    
    FOREIGN KEY (id_cliente) REFERENCES Clientes(Id_Cliente)
);

CREATE TABLE ProveedorTelefono (
    id_telefonoProve INT PRIMARY KEY,
    id_Proveedor INT,
    numero_telefono_P NVARCHAR(10),
    
    FOREIGN KEY (id_Proveedor) REFERENCES Proveedores(id_Proveedor)
);

CREATE TABLE Factura (
    id_factura INT PRIMARY KEY,
    id_cliente INT,
    Id_Usuario INT,
    FechaHora DATETIME,
    Total DECIMAL(10, 2),
    
    FOREIGN KEY (id_cliente) REFERENCES Clientes(Id_Cliente),
    FOREIGN KEY (Id_Usuario) REFERENCES Usuarios(IdUsuario)
);

CREATE TABLE DetalleFactura (
    Id_Detalle INT PRIMARY KEY,
    Id_Factura INT,
    Id_Producto INT,
    cantidad INT,
    Subtotal DECIMAL(10, 2),
    
    FOREIGN KEY (Id_Factura) REFERENCES Factura(id_factura),
    FOREIGN KEY (Id_Producto) REFERENCES Productos(Id_Producto)
);