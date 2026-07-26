"""
Manejo de la tabla reseñas para almacenar el historial crudo escrapeado.
"""
import sqlite3
from modulos.base_datos.conexion import obtener_conexion

def guardar_resenas_masivas(asin: str, resenas: list):
    """Inserta una lista de reseñas en SQLite de forma masiva (Bulk Insert)."""
    if not resenas:
        return
        
    conn = obtener_conexion()
    c = conn.cursor()
    
    # Preparamos los datos en una lista de tuplas para la inserción rápida
    datos_a_insertar = []
    for r in resenas:
        datos_a_insertar.append((
            # 🔴 AQUI ESTÁ EL CAMBIO: Adaptado a las llaves en español de tu extractor local
            r.get("id", ""),
            asin,
            r.get("autor", "Anónimo"),
            r.get("estrellas", 0),
            r.get("titulo_comentario", ""),
            r.get("texto", ""),
            r.get("fecha_publicacion", ""),
            r.get("compra_verificada", False)
        ))
        
    try:
        # INSERT OR IGNORE evita que la base de datos crashee si se intenta 
        # insertar una reseña con un review_id que ya existe
        c.executemany('''
            INSERT OR IGNORE INTO resenas 
            (review_id, asin, author, rating, title, body, fecha, verified)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', datos_a_insertar)
        conn.commit()
        print(f"[SQL] {c.rowcount} reseñas nuevas guardadas en la BD relacional para {asin}.")
    except sqlite3.Error as e:
        print(f"[ERROR DB] No se pudieron guardar las reseñas para {asin}: {e}")
    finally:
        conn.close()