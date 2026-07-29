"""
Registrar métricas de rendimiento del LLM.
"""
import uuid
import json
from datetime import datetime
from modulos.base_datos.conexion import obtener_conexion

def guardar_registro_auditoria(
    session_id: str, user_prompt: str, system_response: str, 
    ttft_ms: float, total_latency_ms: float, tokens_per_second: float, 
    was_blocked: bool = False, tools_executed: list = []
):
    """Guarda las métricas de rendimiento en la tabla de auditoría."""
    conn = obtener_conexion()
    c = conn.cursor()
    
    registro_id = str(uuid.uuid4())
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    tools_json = json.dumps(tools_executed)
    
    c.execute('''
        INSERT INTO auditoria 
        (id, session_id, timestamp, user_prompt, system_response, ttft_ms, total_latency_ms, tokens_per_second, was_blocked, tools_executed)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (registro_id, session_id, timestamp, user_prompt, system_response, ttft_ms, total_latency_ms, tokens_per_second, was_blocked, tools_json))
    
    conn.commit()
    conn.close()

def obtener_ultima_metrica(usuario_id: str):
    """Devuelve el registro más reciente de la tabla de auditoría, filtrado por el usuario actual."""
    conn = obtener_conexion()
    c = conn.cursor()
    
    uid_limpio = str(usuario_id).strip()
    
    # Usamos TRIM() para eliminar espacios ocultos en los UUIDs que rompan la comparación
    c.execute('''
        SELECT a.* 
        FROM auditoria a
        JOIN sesiones s ON TRIM(a.session_id) = TRIM(s.id)
        WHERE TRIM(s.usuario_id) = ?
        ORDER BY a.timestamp DESC LIMIT 1
    ''', (uid_limpio,))
    
    fila = c.fetchone()
    conn.close()
    
    if fila:
        return {
            "id": fila[0], "session_id": fila[1], "timestamp": fila[2],
            "user_prompt": fila[3], "system_response": fila[4], 
            "ttft_ms": fila[5], "total_latency_ms": fila[6], 
            "tokens_per_second": fila[7], "was_blocked": fila[8], 
            "tools_executed": json.loads(fila[9]) if fila[9] else []
        }
    return None

def obtener_metricas_paginadas(limite: int, salto: int, usuario_id: str):
    """Devuelve una lista de registros paginados y el total de elementos, estrictamente del usuario actual."""
    conn = obtener_conexion()
    c = conn.cursor()
    
    uid_limpio = str(usuario_id).strip()
    
    # 1. Total de registros con TRIM
    c.execute('''
        SELECT COUNT(a.id) 
        FROM auditoria a
        JOIN sesiones s ON TRIM(a.session_id) = TRIM(s.id)
        WHERE TRIM(s.usuario_id) = ?
    ''', (uid_limpio,))
    total_registros = c.fetchone()[0]
    
    # 2. Búsqueda con TRIM
    c.execute('''
        SELECT a.* 
        FROM auditoria a
        JOIN sesiones s ON TRIM(a.session_id) = TRIM(s.id)
        WHERE TRIM(s.usuario_id) = ?
        ORDER BY a.timestamp DESC LIMIT ? OFFSET ?
    ''', (uid_limpio, limite, salto))
    
    filas = c.fetchall()
    conn.close()
    
    resultados = []
    for fila in filas:
        resultados.append({
            "id": fila[0], "session_id": fila[1], "timestamp": fila[2],
            "user_prompt": fila[3], "system_response": fila[4], 
            "ttft_ms": fila[5], "total_latency_ms": fila[6], 
            "tokens_per_second": fila[7], "was_blocked": fila[8], 
            "tools_executed": json.loads(fila[9]) if fila[9] else []
        })
        
    return {"total": total_registros, "datos": resultados}