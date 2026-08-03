"""
Control de sesión única por usuario y límite de una cuenta por IP.

IMPORTANTE: esto NO tiene relación con modulos/base_datos/operaciones/sesiones.py
(ese módulo maneja las sesiones de CHAT del RAG: asin, título, mensajes).
Esto es una tabla nueva, exclusiva para el control de acceso del login.

Diseño clave para evitar condiciones de carrera:
- `usuario_id` es PRIMARY KEY -> el motor rechaza una segunda fila para el
  mismo usuario aunque dos requests de login lleguen simultáneamente.
- `ip_address` es UNIQUE -> el motor rechaza una segunda fila con la misma
  IP aunque el chequeo previo en Python haya dicho "IP libre".
Esto significa que la garantía real de "una sesión por usuario y una
cuenta por IP" la da la base de datos, no el chequeo previo (ese chequeo
solo sirve para devolver un mensaje de error claro en el caso normal).
"""
import sqlite3
from datetime import datetime, timezone, timedelta
from modulos.base_datos.conexion import obtener_conexion

# Debe coincidir con COOKIE_MAX_AGE en modulos/api/routes/auth.py
DURACION_SESION = timedelta(hours=2)


def inicializar_tabla_sesiones_activas():
    """Crea la tabla si no existe. Llamar una vez al arrancar la app
    (ej. en el evento de startup de FastAPI, junto a la creación del resto
    de tablas)."""
    conn = obtener_conexion()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS sesiones_activas (
            usuario_id TEXT PRIMARY KEY,
            ip_address TEXT NOT NULL UNIQUE,
            creado_en TEXT NOT NULL,
            expira_en TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()


def _limpiar_expiradas(c, ahora_iso: str):
    """Borra sesiones activas vencidas. Se ejecuta como parte de las
    lecturas para que una sesión vieja no bloquee indefinidamente."""
    c.execute('DELETE FROM sesiones_activas WHERE expira_en < ?', (ahora_iso,))


def obtener_sesion_activa_usuario(usuario_id: str):
    """Devuelve la sesión activa vigente del usuario, o None si no tiene."""
    conn = obtener_conexion()
    c = conn.cursor()
    ahora_iso = datetime.now(timezone.utc).isoformat()
    _limpiar_expiradas(c, ahora_iso)
    conn.commit()
    c.execute(
        'SELECT usuario_id, ip_address, creado_en, expira_en FROM sesiones_activas WHERE usuario_id = ?',
        (usuario_id,)
    )
    fila = c.fetchone()
    conn.close()
    if fila:
        return {"usuario_id": fila[0], "ip_address": fila[1], "creado_en": fila[2], "expira_en": fila[3]}
    return None


def obtener_usuario_activo_por_ip(ip_address: str):
    """Devuelve el usuario_id que tiene sesión activa vigente desde esa IP,
    o None si la IP está libre."""
    conn = obtener_conexion()
    c = conn.cursor()
    ahora_iso = datetime.now(timezone.utc).isoformat()
    _limpiar_expiradas(c, ahora_iso)
    conn.commit()
    c.execute('SELECT usuario_id FROM sesiones_activas WHERE ip_address = ?', (ip_address,))
    fila = c.fetchone()
    conn.close()
    return fila[0] if fila else None


def registrar_sesion_activa(usuario_id: str, ip_address: str) -> bool:
    """
    Crea el registro de sesión activa.
    Devuelve False si, por una condición de carrera, alguien más ganó el
    registro entre el chequeo previo y este insert (usuario_id o
    ip_address ya ocupados) -> en ese caso el caller NO debe dejar pasar
    el login aunque las credenciales sean correctas.
    """
    conn = obtener_conexion()
    c = conn.cursor()
    ahora = datetime.now(timezone.utc)
    expira = ahora + DURACION_SESION
    try:
        _limpiar_expiradas(c, ahora.isoformat())
        c.execute('''
            INSERT INTO sesiones_activas (usuario_id, ip_address, creado_en, expira_en)
            VALUES (?, ?, ?, ?)
        ''', (str(usuario_id), str(ip_address), ahora.isoformat(), expira.isoformat()))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        conn.rollback()
        return False
    except sqlite3.Error as e:
        print(f"[ERROR DB] No se pudo registrar sesión activa para {usuario_id}: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


def eliminar_sesion_activa(usuario_id: str) -> None:
    """Libera la sesión activa del usuario. Llamar en /logout."""
    conn = obtener_conexion()
    c = conn.cursor()
    c.execute('DELETE FROM sesiones_activas WHERE usuario_id = ?', (usuario_id,))
    conn.commit()
    conn.close()