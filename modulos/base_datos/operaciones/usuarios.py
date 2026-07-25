"""
Manejar el registro, la autenticación y la gestión de la tabla usuarios.
"""
import uuid
import sqlite3
from modulos.base_datos.conexion import obtener_conexion

def crear_usuario( nombre: str, apellido: str, correo: str, password_hash: str) -> str:
    """Inserta un nuevo usuario en la BD y retorna su ID."""
    nuevo_id = str(uuid.uuid4())
    conn = obtener_conexion()
    c = conn.cursor()
    try:
        c.execute('INSERT INTO usuarios (id, nombre, apellido, correo, password_hash) VALUES (?, ?, ?, ?, ?)', 
                  (nuevo_id, nombre, apellido, correo, password_hash))
        conn.commit()
        return nuevo_id
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()

def obtener_usuario_por_correo(correo: str):
    """Busca un usuario por su correo. Retorna un diccionario si existe."""
    conn = obtener_conexion()
    c = conn.cursor()
    c.execute('SELECT id, nombre, apellido, correo, password_hash FROM usuarios WHERE correo = ?', (correo,))
    fila = c.fetchone()
    conn.close()
    
    if fila:
        return {"id": fila[0], "nombre": fila[1], "apellido": fila[2], "correo": fila[3], "password_hash": fila[4]}
    return None