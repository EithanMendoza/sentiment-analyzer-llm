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
    """
    Inserta un nuevo producto o re-asigna/actualiza sus metadatos al usuario_id activo
    evitando colisiones de clave primaria (UNIQUE constraint).
    """
    conn = obtener_conexion()
    c = conn.cursor()
    
    asegurar_columna_usuario(c)
    caracteristicas_str = json.dumps(caracteristicas, ensure_ascii=False)
    
    try:
        # 1. Comprobamos si el ASIN existe en la tabla independientemente de quién sea el dueño
        c.execute('SELECT asin FROM productos WHERE asin = ?', (asin,))
        producto_existe = c.fetchone()
        
        if producto_existe:
            # 2. Si el producto ya existe, actualizamos su nombre, características Y se lo re-asignamos al usuario actual
            c.execute('''
                UPDATE productos 
                SET nombre = ?, caracteristicas_json = ?, usuario_id = ? 
                WHERE asin = ?
            ''', (nombre, caracteristicas_str, str(usuario_id), asin))
        else:
            # 3. Si es un producto totalmente nuevo, hacemos el INSERT
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
    AISLAMIENTO ESTRICTO: Devuelve ÚNICAMENTE los productos analizados
    y pertenecientes al usuario autenticado.
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
    Elimina de SQLite únicamente las reseñas y productos vinculados de forma estricta 
    al ID del usuario en sesión, garantizando el aislamiento multiusuario.
    """
    conn = obtener_conexion()
    c = conn.cursor()
    try:
        # Aseguramos que la columna exista para evitar errores de sintaxis
        asegurar_columna_usuario(c)
        
        usuario_str = str(usuario_id)

        # 1. Eliminamos primero las reseñas enlazadas ÚNICAMENTE a productos de este usuario
        c.execute('''
            DELETE FROM resenas 
            WHERE asin IN (
                SELECT asin FROM productos 
                WHERE usuario_id = ?
            )
        ''', (usuario_str,))
        
        # 2. Eliminamos los productos vinculados estrictamente al usuario en sesión
        c.execute('''
            DELETE FROM productos 
            WHERE usuario_id = ?
        ''', (usuario_str,))
        
        conn.commit()
        print(f"[SQLITE] Limpieza exitosa y aislada completada para el usuario: {usuario_str}")
    except sqlite3.Error as e:
        print(f"[ERROR SQLITE] Falló al eliminar registros del usuario {usuario_id}: {e}")
        conn.rollback()
    finally:
        conn.close()