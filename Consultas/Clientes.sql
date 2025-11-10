use django_sqlserver;

Insert into Clientes(Id_Cliente,Nombre,Apellido)Values
(345,'Claudia','Ramirez');

Insert into ClienteTelefono(id_telefonoCli,id_cliente,numero_telefono_C)Values
(5893,345,'72893012');+

 select * from Clientes ;
 select * from ClienteTelefono;

 delete from Clientes where Id_Cliente=345;
 delete from ClienteTelefono where id_telefonoCli=5893;