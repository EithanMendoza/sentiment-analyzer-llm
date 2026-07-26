"""
Manejo de la tabla productos para almacenar metadatos oficiales de Amazon.
"""
import json
import sqlite3
from modulos.base_datos.conexion import obtener_conexion

def asegurar_columna_usuario(c):
    """Verifica si la columna usuario_id existe en la tabla productos; si no, la agrega."""
    c.execute("PRAGMA table_info(productos)")
    columnas = [columna[1] for columna in c.fetchall()]
    if "usuario_id" not in columnas:
        try:
            c.execute("ALTER TABLE productos ADD COLUMN usuario_id TEXT")
            print("[SQLITE] Columna 'usuario_id' añadida exitosamente a la tabla productos.")
        except sqlite3.Error as e:
            print(f"[SQLITE ERROR ALTER] No se pudo agregar la columna usuario_id: {e}")

def guardar_o_actualizar_producto(asin: str, nombre: str, caracteristicas: list, usuario_id: str = "desconocido"):
    """Inserta un nuevo producto vinculado al usuario o actualiza sus datos si ya existe."""
    conn = obtener_conexion()
    c = conn.cursor()
    
    # Nos aseguramos de que la columna usuario_id exista antes de operar
    asegurar_columna_usuario(c)
    
    caracteristicas_str = json.dumps(caracteristicas, ensure_ascii=False)
    
    try:
        # 1. Comprobamos si el ASIN ya está registrado para ESTE usuario específico
        c.execute('SELECT asin FROM productos WHERE asin = ? AND usuario_id = ?', (asin, str(usuario_id)))
        producto_existe = c.fetchone()
        
        if producto_existe:
            # 2. Si existe, actualizamos sus valores
            c.execute('''
                UPDATE productos 
                SET nombre = ?, caracteristicas_json = ? 
                WHERE asin = ? AND usuario_id = ?
            ''', (nombre, caracteristicas_str, asin, str(usuario_id)))
        else:
            # 3. Si no existe, creamos el registro amarrado al usuario_id
            c.execute('''
                INSERT INTO productos (asin, nombre, caracteristicas_json, usuario_id) 
                VALUES (?, ?, ?, ?)
            ''', (asin, nombre, caracteristicas_str, str(usuario_id)))
            
        conn.commit()
    except sqlite3.Error as e:
        print(f"[ERROR DB] No se pudo guardar el producto {asin} para el usuario {usuario_id}: {e}")
    finally:
        conn.close()

def obtener_todos_los_productos():
    """
    [MÉTODO GLOBAL]: Devuelve todos los productos sin filtrar (Historial general).
    """
    conn = obtener_conexion()
    c = conn.cursor()
    c.execute('SELECT asin, nombre FROM productos ORDER BY rowid DESC')
    filas = c.fetchall()
    conn.close()
    return [{"asin": fila[0], "nombre": fila[1]} for fila in filas]

def obtener_productos_por_usuario(usuario_id: str) -> list:
    """
    [NUEVO MÈTODO DE AISLAMIENTO]: Devuelve ÚNICAMENTE los productos analizados
    por el usuario autenticado. Ideal para poblar el combobox del Frontend en 'Chat nuevo'.
    """
    conn = obtener_conexion()
    c = conn.cursor()
    try:
        asegurar_columna_usuario(c)
        c.execute('''
            SELECT asin, nombre 
            FROM productos 
            WHERE usuario_id = ? 
            ORDER BY rowid DESC
        ''', (str(usuario_id),))
        filas = c.fetchall()
        return [{"asin": fila[0], "nombre": fila[1]} for fila in filas]
    except sqlite3.Error as e:
        print(f"[ERROR SQLITE] No se pudieron listar los productos del usuario {usuario_id}: {e}")
        return []
    finally:
        conn.close()

def obtener_producto(asin: str, usuario_id: str = None):
    """
    Recupera los metadatos de un producto filtrando opcionalmente por usuario
    para garantizar el aislamiento de datos (Vía Rápida).
    """
    conn = obtener_conexion()
    c = conn.cursor()
    try:
        asegurar_columna_usuario(c)
        if usuario_id:
            c.execute('''
                SELECT asin, nombre, caracteristicas_json 
                FROM productos 
                WHERE asin = ? AND usuario_id = ?
            ''', (asin, str(usuario_id)))
        else:
            c.execute('SELECT asin, nombre, caracteristicas_json FROM productos WHERE asin = ?', (asin,))
            
        fila = c.fetchone()
        if fila:
            return {
                "asin": fila[0], 
                "nombre": fila[1], 
                "caracteristicas": json.loads(fila[2]) if fila[2] else []
            }
        return None
    except sqlite3.Error as e:
        print(f"[ERROR SQLITE] Error al obtener el producto {asin}: {e}")
        return None
    finally:
        conn.close()

def vaciar_productos_por_usuario(usuario_id: str):
    """
    ELIMINACIÓN ESTRICTA Y AISLADA:
    Elimina de SQLite únicamente las reseñas y productos vinculados al id de este usuario,
    así como posibles registros huérfanos generados en etapas de desarrollo tempranas.
    """
    conn = obtener_conexion()
    c = conn.cursor()
    try:
        # Aseguramos que la columna exista para evitar errores de sintaxis
        asegurar_columna_usuario(c)
        
        # 1. Eliminamos primero las reseñas enlazadas a los productos del usuario u huérfanos
        c.execute('''
            DELETE FROM resenas 
            WHERE asin IN (
                SELECT asin FROM productos 
                WHERE usuario_id = ? OR usuario_id IS NULL OR usuario_id = 'desconocido'
            )
        ''', (str(usuario_id),))
        
        # 2. Eliminamos los productos vinculados estrictamente al usuario u huérfanos
        c.execute('''
            DELETE FROM productos 
            WHERE usuario_id = ? OR usuario_id IS NULL OR usuario_id = 'desconocido'
        ''', (str(usuario_id),))
        
        conn.commit()
        print(f"[SQLITE] Limpieza exitosa y aislada (incluyendo huérfanos) para el usuario: {usuario_id}")
    except sqlite3.Error as e:
        print(f"[ERROR SQLITE] Falló al eliminar registros del usuario {usuario_id}: {e}")
        conn.rollback()
    finally:
        conn.close()