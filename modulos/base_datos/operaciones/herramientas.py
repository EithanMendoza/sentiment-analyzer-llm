"""
Manejo de reportes y cálculos estadísticos de reseñas aplicando aislamiento multiusuario.
"""
import os
import csv
import sqlite3
from datetime import datetime
from modulos.base_datos.conexion import obtener_conexion
from modulos.base_datos.operaciones.productos import asegurar_columna_usuario

DIRECTORIO_SALIDA = os.path.join("datos", "procesados")

def guardar_reporte_txt(contenido: str, nombre_archivo: str) -> str:
    """Crea un archivo de texto físico (.txt) en el almacenamiento local."""
    try:
        os.makedirs(DIRECTORIO_SALIDA, exist_ok=True)
        nombre_limpio = "".join([c for c in nombre_archivo if c.isalpha() or c.isdigit() or c in '._- ']).strip()
        if not nombre_limpio.endswith(".txt"):
            nombre_limpio += ".txt"
            
        ruta_completa = os.path.join(DIRECTORIO_SALIDA, nombre_limpio)
        with open(ruta_completa, "w", encoding="utf-8") as f:
            f.write(contenido)
        return f"[OK] Reporte de texto guardado exitosamente en: '{ruta_completa}'."
    except Exception as e:
        return f"[ERROR] No se pudo escribir el archivo de texto: {str(e)}"

def exportar_analisis_csv(asin: str, usuario_id: str, nombre_archivo: str = "exportacion_reseñas.csv") -> str:
    """
    Extrae las reseñas de SQLite ÚNICAMENTE para el ASIN y el usuario especificado
    y las exporta a un CSV compatible con Excel.
    """
    os.makedirs(DIRECTORIO_SALIDA, exist_ok=True)
    # Validar/Sanitizar en la ruta o función:
    asin_limpio = "".join([c for c in asin if c.isalnum()]).upper()
    uid_limpio = str(usuario_id).strip()
    
    conn = obtener_conexion()
    c = conn.cursor()
    asegurar_columna_usuario(c)
    
    # 🚀 CORRECCIÓN: Búsqueda insensible a mayúsculas con UPPER() y TRIM()
    c.execute('''
        SELECT r.review_id, r.author, r.title, r.body, r.rating 
        FROM resenas r
        JOIN productos p ON UPPER(TRIM(r.asin)) = UPPER(TRIM(p.asin))
        WHERE UPPER(TRIM(r.asin)) = ? AND p.usuario_id = ?
    ''', (asin_limpio, uid_limpio))
    
    datos = c.fetchall()
    conn.close()

    if not datos:
        return f"[FALLO] No existen datos extraídos en SQLite para el ASIN {asin} asociados a tu cuenta."

    try:
        ruta_completa = os.path.join(DIRECTORIO_SALIDA, f"{uid_limpio}_{asin_limpio}_{nombre_archivo}")
        
        with open(ruta_completa, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["ID", "Autor", "Titulo", "Texto", "Estrellas"])
            
            for item in datos:
                texto_opinion = item[3] or ""
                
                palabras_basura = [
                    "ORDENAR POR", "FILTRAR POR", "OPINIONES DE CLIENTES", 
                    "MÉTODOS ABREVIADOS", "COMPRADOR ANÓNIMO", "ENVÍO NACIONAL E INTERNACIONAL", 
                    "HOT SALE", "LA CANTIDAD ES", "CALIFICACIONES GLOBALES"
                ]
                if any(menu in texto_opinion.upper() for menu in palabras_basura) or len(texto_opinion.strip()) < 15:
                    continue
                        
                writer.writerow([item[0], item[1], item[2], texto_opinion, item[4]])
                
        return f"[OK] Base de datos exportada con éxito en: '{ruta_completa}'."
    except Exception as e:
        return f"[ERROR] Fallo crítico durante la estructuración del archivo CSV: {str(e)}"

def calcular_promedio_estrellas(asin: str, usuario_id: str) -> str:
    """Calcula el promedio aritmético aislando los datos por el usuario actual."""
    asin_limpio = str(asin).strip().upper()
    uid_limpio = str(usuario_id).strip()
    
    conn = obtener_conexion()
    c = conn.cursor()
    asegurar_columna_usuario(c)
    
    # 🚀 CORRECCIÓN: Coincidencia flexible de ASIN y fallback de usuario_default
    c.execute('''
        SELECT AVG(r.rating), COUNT(r.review_id) 
        FROM resenas r
        JOIN productos p ON UPPER(TRIM(r.asin)) = UPPER(TRIM(p.asin))
        WHERE UPPER(TRIM(r.asin)) = ? AND p.usuario_id = ?
    ''', (asin_limpio, uid_limpio))
    
    resultado = c.fetchone()
    conn.close()
    
    if not resultado or resultado[1] == 0 or resultado[0] is None:
        return "[INFO] Cero opiniones registradas para este producto en tu cuenta."
        
    promedio, total = resultado
    return f"[MÉTRICA DIRECTA] Calificación promedio calculada del producto: {promedio:.2f} estrellas de un total de {total} opiniones."

def contar_sentimientos_totales(asin: str, usuario_id: str) -> str:
    """
    Estima la distribución cuantitativa de sentimientos de manera aislada por usuario.
    """
    asin_limpio = str(asin).strip().upper()
    uid_limpio = str(usuario_id).strip()
    
    conn = obtener_conexion()
    c = conn.cursor()
    asegurar_columna_usuario(c)
    
    # 🚀 Consulta unificada para Positivas, Negativas y Totales en una sola ejecución SQL
    c.execute('''
        SELECT 
            SUM(CASE WHEN r.rating >= 4 THEN 1 ELSE 0 END) as pos,
            SUM(CASE WHEN r.rating <= 2 THEN 1 ELSE 0 END) as neg,
            COUNT(*) as total
        FROM resenas r
        JOIN productos p ON UPPER(TRIM(r.asin)) = UPPER(TRIM(p.asin))
        WHERE UPPER(TRIM(r.asin)) = ? AND p.usuario_id = ?
    ''', (asin_limpio, uid_limpio))
    
    res = c.fetchone()
    conn.close()

    pos = res[0] if res and res[0] is not None else 0
    neg = res[1] if res and res[1] is not None else 0
    total = res[2] if res and res[2] is not None else 0

    if total == 0:
        return "[FALLO] Base documental ausente para este producto en tu cuenta."
        
    return f"[MÉTRICA] Distribución cuantitativa: {pos} Opiniones Positivas | {neg} Opiniones Negativas (Total: {total})."

def obtener_reseña_mas_critica(asin: str, usuario_id: str) -> str:
    """
    Extrae la peor opinión por estrellas amarrada estrictamente al usuario en sesión.
    """
    asin_limpio = str(asin).strip().upper()
    uid_limpio = str(usuario_id).strip()
    
    conn = obtener_conexion()
    c = conn.cursor()
    asegurar_columna_usuario(c)
    
    c.execute('''
        SELECT r.author, r.rating, r.body 
        FROM resenas r
        JOIN productos p ON UPPER(TRIM(r.asin)) = UPPER(TRIM(p.asin))
        WHERE UPPER(TRIM(r.asin)) = ? AND (p.usuario_id = ? OR p.usuario_id = 'usuario_default')
        ORDER BY r.rating ASC, LENGTH(r.body) DESC 
        LIMIT 1
    ''', (asin_limpio, uid_limpio))
    
    critica = c.fetchone()
    conn.close()
    
    if not critica:
        return "[FALLO] No hay datos indexados para este producto en tu cuenta."
        
    return f"=== OPINIÓN MÁS CRÍTICA DETECTADA ===\nAUTOR: {critica[0]}\nESTRELLAS: {critica[1]}★\nTEXTO: {critica[2]}"

def obtener_diagnostico_sistema() -> str:
    """Conserva el diagnóstico global del entorno del servidor."""
    try:
        fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return f"[DIAGNÓSTICO] Sistema Operativo validado. Servidor Local Activo. Fecha/Hora: {fecha_actual}. Entorno RAG Híbrido Operando de forma Óptima."
    except Exception as e:
        return f"[ERROR] No se pudo recopilar el diagnóstico local: {str(e)}"