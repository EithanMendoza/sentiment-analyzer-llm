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

def obtener_ultima_metrica():
    """Devuelve el registro más reciente de la tabla de auditoría."""
    conn = obtener_conexion()
    c = conn.cursor()
    # Usamos ORDER BY timestamp DESC para ordenar de más nuevo a más viejo y LIMIT 1
    c.execute('SELECT * FROM auditoria ORDER BY timestamp DESC LIMIT 1')
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

def obtener_metricas_paginadas(limite: int = 10, salto: int = 0):
    """Devuelve una lista de registros paginados y el total de elementos."""
    conn = obtener_conexion()
    c = conn.cursor()
    
    # 1. Obtener el total de registros para que el frontend pueda calcular las páginas
    c.execute('SELECT COUNT(*) FROM auditoria')
    total_registros = c.fetchone()[0]
    
    # 2. Obtener los registros limitados usando OFFSET para saltar
    c.execute('SELECT * FROM auditoria ORDER BY timestamp DESC LIMIT ? OFFSET ?', (limite, salto))
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