USE django_sqlserver

Insert into Usuarios(IdUsuario,Nombre,Contraseña,Rol)Values
(556,'Yoseling','1234','Admin');

ALTER TABLE Usuarios
ALTER COLUMN Contraseña NVARCHAR(255);
GO

UPDATE Usuarios
SET Contraseña = 'pbkdf2_sha256$1000000$vr5mT4bphQe3BqmRgcTc7t$jcMRObhqiNbrV6j6uThmovcM94iID4yQGVIROWA7eWo='
WHERE IdUsuario = 556;
GO

select * from Usuarios

--dj@ng0