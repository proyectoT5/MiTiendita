from django.db import connection
from django.contrib.auth.hashers import make_password

# --- CONFIGURACIÓN ---
NUEVA_CLAVE = "12345"  # <--- Escribe aquí tu nueva contraseña temporal
USUARIO_OBJETIVO = "Yoseling" # <--- Escribe aquí el NOMBRE exacto de tu usuario administrador

# 1. Generamos el hash seguro (igual que en tu views.py)
hash_seguro = make_password(NUEVA_CLAVE)

# 2. Ejecutamos el UPDATE directo a tu tabla 'Usuarios'
with connection.cursor() as cursor:
    # Verificamos si existe primero para que no te asustes si no actualiza nada
    cursor.execute("SELECT count(*) FROM Usuarios WHERE Nombre = %s", [USUARIO_OBJETIVO])
    existe = cursor.fetchone()[0]
    
    if existe:
        cursor.execute("UPDATE Usuarios SET Contraseña = %s WHERE Nombre = %s", [hash_seguro, USUARIO_OBJETIVO])
        print(f"\n✅ ÉXITO: La contraseña para '{USUARIO_OBJETIVO}' ha sido cambiada a '{NUEVA_CLAVE}'.")
    else:
        print(f"\n❌ ERROR: No se encontró el usuario '{USUARIO_OBJETIVO}'. Revisa si está escrito con mayúsculas/minúsculas correctas.")