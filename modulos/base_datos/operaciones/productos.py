"""
Manejo de la tabla productos para almacenar metadatos oficiales de Amazon.
"""
import json
import sqlite3
from modulos.base_datos.conexion import obtener_conexion

def guardar_o_actualizar_producto(asin: str, nombre: str, caracteristicas: list):
    """Inserta un nuevo producto o actualiza sus datos si ya existe."""
    conn = obtener_conexion()
    c = conn.cursor()
    
    # Convertimos la lista de características a un string JSON para guardarlo en TEXT
    caracteristicas_str = json.dumps(caracteristicas, ensure_ascii=False)
    
    try:
        # 1. Comprobamos de forma manual si el ASIN ya está registrado
        c.execute('SELECT asin FROM productos WHERE asin = ?', (asin,))
        producto_existe = c.fetchone()
        
        if producto_existe:
            # 2. Si existe, actualizamos sus valores
            c.execute('''
                UPDATE productos 
                SET nombre = ?, caracteristicas_json = ? 
                WHERE asin = ?
            ''', (nombre, caracteristicas_str, asin))
        else:
            # 3. Si no existe, creamos el registro nuevo
            c.execute('''
                INSERT INTO productos (asin, nombre, caracteristicas_json) 
                VALUES (?, ?, ?)
            ''', (asin, nombre, caracteristicas_str))
            
        conn.commit()
    except sqlite3.Error as e:
        print(f"[ERROR DB] No se pudo guardar el producto {asin}: {e}")
    finally:
        conn.close()

def obtener_todos_los_productos():
    """
    Devuelve todos los productos ya analizados (asin + nombre).
    Se usa para el selector de 'Chat nuevo', donde el usuario elige sobre
    qué producto ya analizado quiere seguir preguntando.
    Ordenado por rowid descendente como aproximación de "más reciente primero"
    (la tabla no tiene columna de fecha; si el producto se actualiza con
    guardar_o_actualizar_producto, conserva su rowid original).
    """
    conn = obtener_conexion()
    c = conn.cursor()
    c.execute('SELECT asin, nombre FROM productos ORDER BY rowid DESC')
    filas = c.fetchall()
    conn.close()
    return [{"asin": fila[0], "nombre": fila[1]} for fila in filas]

def obtener_producto(asin: str):
    """Recupera los metadatos de un producto. Retorna un diccionario."""
    conn = obtener_conexion()
    c = conn.cursor()
    c.execute('SELECT asin, nombre, caracteristicas_json FROM productos WHERE asin = ?', (asin,))
    fila = c.fetchone()
    conn.close()
    
    if fila:
        return {
            "asin": fila[0], 
            "nombre": fila[1], 
            "caracteristicas": json.loads(fila[2]) if fila[2] else []
        }
    return None