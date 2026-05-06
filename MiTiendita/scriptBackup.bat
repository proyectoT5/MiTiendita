@echo off

:: Ruta base del proyecto
set PROYECTO=C:\Users\Godoy\OneDrive\Desktop\MiTiendita\MiTiendita

:: Carpeta de backups
set BACKUP=%PROYECTO%\backups

:: Crear carpeta si no existe
if not exist "%BACKUP%" (
    mkdir "%BACKUP%"
)

:: Obtener fecha
for /f %%i in ('powershell -Command "Get-Date -Format yyyy-MM-dd"') do set FECHA=%%i

:: Copiar base de datos
copy "%PROYECTO%\db.sqlite3" "%BACKUP%\db_%FECHA%.sqlite3"

echo Backup realizado correctamente: %FECHA%

pause