"""
Administrar las sesiones de chat y almacenar el historial de mensajes crudos.
"""
import sqlite3
import uuid
from modulos.base_datos.conexion import obtener_conexion

def crear_sesion_si_no_existe(sesion_id: str, asin: str, usuario_id: str, primer_mensaje: str = None):
    """
    Verifica si la sesión existe. Si no, la crea con un título dinámico 
    asociado al usuario legítimo y al ASIN del producto.
    """
    conn = obtener_conexion()
    c = conn.cursor()
    try:
        if primer_mensaje:
            palabras = primer_mensaje.split()
            titulo_chat = " ".join(palabras[:5]) + ("..." if len(palabras) > 5 else "")
        else:
            titulo_chat = f"Análisis de {asin}"
        
        # Insertamos la sesión vinculada al usuario autenticado (sin crear usuarios ficticios)
        c.execute('''
            INSERT OR IGNORE INTO sesiones (id, usuario_id, asin, titulo) 
            VALUES (?, ?, ?, ?)
        ''', (str(sesion_id), str(usuario_id), str(asin), titulo_chat))
        
        conn.commit()
    except sqlite3.Error as e:
        print(f"[ERROR DB] No se pudo crear o verificar la sesión {sesion_id}: {e}")
        conn.rollback()
    finally:
        conn.close()


def crear_sesion(usuario_id: str, asin: str, titulo: str) -> str:
    """
    Crea una nueva sesión de chat de forma explícita generando un UUID único.
    Devuelve el ID generado para que el frontend pueda redirigir al chat.
    """
    nuevo_id = str(uuid.uuid4())
    conn = obtener_conexion()
    c = conn.cursor()
    
    try:
        c.execute('''
            INSERT INTO sesiones (id, usuario_id, asin, titulo) 
            VALUES (?, ?, ?, ?)
        ''', (nuevo_id, str(usuario_id), str(asin), titulo))
        
        conn.commit()
        return nuevo_id
    except sqlite3.Error as e:
        print(f"[ERROR DB] No se pudo crear la sesión explícita: {e}")
        conn.rollback()
        return None
    finally:
        conn.close()

def guardar_mensaje(sesion_id: str, rol: str, contenido: str, asin: str, usuario_id: str = "usuario_default"):
    """Inserta un nuevo mensaje e inicializa la sesión si es la primera vez."""
    # Pasamos el asin por si la sesión necesita ser creada en este momento
    crear_sesion_si_no_existe(sesion_id, asin, usuario_id, primer_mensaje=contenido if rol == 'user' else None)
    
    conn = obtener_conexion()
    c = conn.cursor()
    
    c.execute('''INSERT INTO mensajes (sesion_id, rol, contenido) 
                 VALUES (?, ?, ?)''', (sesion_id, rol, contenido))
    
    conn.commit()
    conn.close()

def obtener_sesiones_por_usuario(usuario_id: str) -> list:
    """Devuelve todas las sesiones de un usuario, ordenadas, incluyendo el ASIN."""
    conn = obtener_conexion()
    c = conn.cursor()
    
    c.execute('''
        SELECT id, asin, titulo, creado_en 
        FROM sesiones 
        WHERE usuario_id = ? 
        ORDER BY creado_en DESC
    ''', (usuario_id,))
    
    filas = c.fetchall()
    conn.close()
    return [{"id": fila[0], "asin": fila[1], "titulo": fila[2], "creado_en": fila[3]} for fila in filas]

def obtener_mensajes_por_sesion(sesion_id: str, usuario_id: str) -> list:
    """Devuelve los mensajes validando que el usuario sea dueño de la sesión."""
    conn = obtener_conexion()
    c = conn.cursor()
    
    c.execute('SELECT id FROM sesiones WHERE id = ? AND usuario_id = ?', (sesion_id, usuario_id))
    if not c.fetchone():
        conn.close()
        return None
        
    c.execute('''
        SELECT rol, contenido, creado_en 
        FROM mensajes 
        WHERE sesion_id = ? 
        ORDER BY id ASC
    ''', (sesion_id,))
    
    filas = c.fetchall()
    conn.close()
    return [{"rol": fila[0], "contenido": fila[1], "creado_en": fila[2]} for fila in filas]

def obtener_historial_crudo(sesion_id: str) -> list:
    """Recupera únicamente rol y contenido para formateo interno de IA."""
    conn = obtener_conexion()
    c = conn.cursor()
    c.execute('SELECT rol, contenido FROM mensajes WHERE sesion_id = ? ORDER BY id ASC', (sesion_id,))
    filas = c.fetchall()
    conn.close()
    return filas

def eliminar_sesion_db(sesion_id: str, usuario_id: str) -> bool:
    """Elimina una sesión específica verificando propiedad."""
    conn = obtener_conexion()
    c = conn.cursor()
    
    c.execute('DELETE FROM sesiones WHERE id = ? AND usuario_id = ?', (sesion_id, usuario_id))
    filas_borradas = c.rowcount
    
    conn.commit()
    conn.close()
    return filas_borradas > 0

# --- NUEVA FUNCIÓN AÑADIDA PARA LÓGICA DE ENRUTAMIENTO ---
def obtener_detalles_sesion(sesion_id: str):
    """Recupera los datos de la sesión (útil para saber a qué ASIN filtrar en ChromaDB)."""
    conn = obtener_conexion()
    c = conn.cursor()
    c.execute('SELECT id, usuario_id, asin, titulo, creado_en FROM sesiones WHERE id = ?', (sesion_id,))
    fila = c.fetchone()
    conn.close()
    
    if fila:
        return {"id": fila[0], "usuario_id": fila[1], "asin": fila[2], "titulo": fila[3], "creado_en": fila[4]}
    return None


def eliminar_todas_las_sesiones_del_usuario(usuario_id: str) -> bool:
    """
    Elimina todas las sesiones y sus respectivos mensajes asociados 
    únicamente al usuario en sesión.
    """
    conn = obtener_conexion()
    c = conn.cursor()
    try:
        # 1. Eliminamos los mensajes de las sesiones de este usuario
        c.execute('''
            DELETE FROM mensajes 
            WHERE sesion_id IN (SELECT id FROM sesiones WHERE usuario_id = ?)
        ''', (str(usuario_id),))
        
        # 2. Eliminamos las sesiones del usuario
        c.execute('DELETE FROM sesiones WHERE usuario_id = ?', (str(usuario_id),))
        
        conn.commit()
        print(f"[SQLITE] Historial de conversaciones eliminado para el usuario: {usuario_id}")
        return True
    except sqlite3.Error as e:
        print(f"[ERROR SQLITE] Falló la eliminación del historial para {usuario_id}: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()