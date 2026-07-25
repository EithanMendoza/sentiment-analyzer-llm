"""
Gestión de la ruta física y conexión a SQLite.
"""
import os
import sqlite3

# Obtiene la ruta absoluta del directorio raíz del proyecto (subiendo dos niveles desde modulos/base_datos)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Construye la ruta: /AgenteLocalParaResenas/datos/base_relacional/historial_sesiones.db
RUTA_DB_RELACIONAL = os.path.join(BASE_DIR, "datos", "base_relacional", "historial_sesiones.db")

def obtener_conexion():
    """Devuelve una conexión a la base de datos con las llaves foráneas activadas."""
    # Aseguramos que la carpeta exista antes de conectar
    os.makedirs(os.path.dirname(RUTA_DB_RELACIONAL), exist_ok=True)
    conn = sqlite3.connect(RUTA_DB_RELACIONAL)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn