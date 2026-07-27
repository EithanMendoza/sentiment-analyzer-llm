"""
Manejo de la tabla reseñas para almacenar el historial crudo escrapeado.
"""
import sqlite3
from modulos.base_datos.conexion import obtener_conexion

def guardar_resenas_masivas(asin: str, resenas: list):
    """Inserta una lista de reseñas en SQLite de forma masiva (Bulk Insert)."""
    if not resenas:
        print(f"[SQL WARNING] No hay reseñas recibidas para almacenar para el ASIN: {asin}")
        return
        
    asin_limpio = str(asin).strip().upper()
    conn = obtener_conexion()
    c = conn.cursor()
    
    # 1. Nos aseguramos de que la tabla exista con la estructura correcta (PK compuesta)
    c.execute('''
        CREATE TABLE IF NOT EXISTS resenas (
            review_id TEXT,
            asin TEXT,
            author TEXT,
            title TEXT,
            body TEXT,
            rating INTEGER,
            fecha TEXT,
            verified BOOLEAN,
            PRIMARY KEY (review_id, asin)
        )
    ''')

    # 2. Migración one-time: si existe una tabla vieja con PK solo en review_id,
    #    la reemplazamos por la de PK compuesta (review_id, asin).
    #    Esto se ejecuta automáticamente en cualquier máquina (la tuya o la de
    #    tus compañeros) la primera vez que corran el código actualizado.
    c.execute("PRAGMA table_info(resenas)")
    columnas_info = c.fetchall()
    pk_columnas = [col[1] for col in columnas_info if col[5] > 0]  # col[5] = orden en la PK (>0 si es parte de ella)

    if pk_columnas == ["review_id"]:
        print("[MIGRACIÓN] Detectada PK antigua en 'resenas'. Migrando a PK compuesta (review_id, asin)...")
        c.execute("ALTER TABLE resenas RENAME TO resenas_old")
        c.execute('''
            CREATE TABLE resenas (
                review_id TEXT,
                asin TEXT,
                author TEXT,
                title TEXT,
                body TEXT,
                rating INTEGER,
                fecha TEXT,
                verified BOOLEAN,
                PRIMARY KEY (review_id, asin)
            )
        ''')
        c.execute('''
            INSERT OR IGNORE INTO resenas (review_id, asin, author, title, body, rating, fecha, verified)
            SELECT review_id, asin, author, title, body, rating, fecha, verified FROM resenas_old
        ''')
        c.execute("DROP TABLE resenas_old")
        conn.commit()
        print("[MIGRACIÓN] Completada exitosamente.")

    # 3. Preparamos los datos en una lista de tuplas con las llaves flexibles
    #    (soporta llaves en español 'autor'/'texto' y en inglés 'author'/'body')
    datos_a_insertar = []
    for r in resenas:
        review_id = str(r.get("id") or r.get("review_id") or "").strip()
        if not review_id:
            continue  # Ignoramos registros sin ID único

        autor = r.get("autor") or r.get("author") or "Anónimo"
        rating = r.get("estrellas") if r.get("estrellas") is not None else r.get("rating", 0)
        titulo = r.get("titulo_comentario") or r.get("title") or "Sin título"
        cuerpo = r.get("texto") or r.get("body") or ""
        fecha = r.get("fecha_publicacion") or r.get("fecha") or ""
        verificada = r.get("compra_verificada") if r.get("compra_verificada") is not None else r.get("verified", False)

        # 🚀 ORDEN EXACTO DE LAS COLUMNAS SQL:
        # (review_id, asin, author, title, body, rating, fecha, verified)
        datos_a_insertar.append((
            review_id,
            asin_limpio,
            autor,
            titulo,
            cuerpo,
            int(rating),
            fecha,
            1 if verificada else 0
        ))
        
    try:
        # INSERT OR REPLACE actualiza la reseña si vuelve a ingresar con el mismo
        # (review_id, asin) — ya no pisa reseñas de otros productos.
        c.executemany('''
            INSERT OR REPLACE INTO resenas 
            (review_id, asin, author, title, body, rating, fecha, verified)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', datos_a_insertar)
        
        conn.commit()
        print(f"[SQL] {len(datos_a_insertar)} reseñas procesadas/guardadas exitosamente en la BD para {asin_limpio}.")
    except sqlite3.Error as e:
        print(f"[ERROR DB] No se pudieron guardar las reseñas para {asin_limpio}: {e}")
    finally:
        conn.close()