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
        c.execute('''
            INSERT INTO productos (asin, nombre, caracteristicas_json) 
            VALUES (?, ?, ?)
            ON CONFLICT(asin) DO UPDATE SET 
                nombre=excluded.nombre,
                caracteristicas_json=excluded.caracteristicas_json
        ''', (asin, nombre, caracteristicas_str))
        conn.commit()
    except sqlite3.Error as e:
        print(f"[ERROR DB] No se pudo guardar el producto {asin}: {e}")
    finally:
        conn.close()

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