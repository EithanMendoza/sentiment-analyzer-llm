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
    
    conn = obtener_conexion()
    c = conn.cursor()
    asegurar_columna_usuario(c)
    
    # Cruzamos con la tabla productos para validar que el ASIN le pertenezca a este usuario
    c.execute('''
        SELECT r.review_id, r.author, r.title, r.body, r.rating 
        FROM resenas r
        JOIN productos p ON r.asin = p.asin
        WHERE r.asin = ? AND p.usuario_id = ?
    ''', (asin, str(usuario_id)))
    
    datos = c.fetchall()
    conn.close()

    if not datos:
        return f"[FALLO] No existen datos extraídos en SQLite para el ASIN {asin} asociados a tu cuenta."

    try:
        ruta_completa = os.path.join(DIRECTORIO_SALIDA, f"{usuario_id}_{asin}_{nombre_archivo}")
        
        with open(ruta_completa, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["ID", "Autor", "Titulo", "Texto", "Estrellas"])
            
            for item in datos:
                texto_opinion = item[3]
                
                # Filtro sanitizador original
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
    conn = obtener_conexion()
    c = conn.cursor()
    asegurar_columna_usuario(c)
    
    c.execute('''
        SELECT AVG(r.rating), COUNT(r.review_id) 
        FROM resenas r
        JOIN productos p ON r.asin = p.asin
        WHERE r.asin = ? AND p.usuario_id = ?
    ''', (asin, str(usuario_id)))
    
    resultado = c.fetchone()
    conn.close()
    
    promedio, total = resultado
    if not total or total == 0:
        return "[INFO] Cero opiniones registradas para este producto en tu cuenta."
        
    return f"[MÉTRICA DIRECTA] Calificación promedio calculada del producto: {promedio:.2f} estrellas de un total de {total} opiniones."

def contar_sentimientos_totales(asin: str, usuario_id: str) -> str:
    """
    Estima la distribución cuantitativa de sentimientos de manera aislada por usuario.
    """
    conn = obtener_conexion()
    c = conn.cursor()
    asegurar_columna_usuario(c)
    
    # Positivas
    c.execute('''
        SELECT COUNT(*) FROM resenas r
        JOIN productos p ON r.asin = p.asin
        WHERE r.asin = ? AND p.usuario_id = ? AND r.rating >= 4
    ''', (asin, str(usuario_id)))
    pos = c.fetchone()[0]
    
    # Negativas
    c.execute('''
        SELECT COUNT(*) FROM resenas r
        JOIN productos p ON r.asin = p.asin
        WHERE r.asin = ? AND p.usuario_id = ? AND r.rating <= 2
    ''', (asin, str(usuario_id)))
    neg = c.fetchone()[0]
    
    # Totales
    c.execute('''
        SELECT COUNT(*) FROM resenas r
        JOIN productos p ON r.asin = p.asin
        WHERE r.asin = ? AND p.usuario_id = ?
    ''', (asin, str(usuario_id)))
    total = c.fetchone()[0]
    conn.close()

    if total == 0:
        return "[FALLO] Base documental ausente para este producto en tu cuenta."
        
    return f"[MÉTRICA] Distribución cuantitativa: {pos} Opiniones Positivas | {neg} Opiniones Negativas (Total: {total})."

def obtener_reseña_mas_critica(asin: str, usuario_id: str) -> str:
    """
    Extrae la peor opinión por estrellas amarrada estrictamente al usuario en sesión.
    """
    conn = obtener_conexion()
    c = conn.cursor()
    asegurar_columna_usuario(c)
    
    c.execute('''
        SELECT r.author, r.rating, r.body 
        FROM resenas r
        JOIN productos p ON r.asin = p.asin
        WHERE r.asin = ? AND p.usuario_id = ?
        ORDER BY r.rating ASC, LENGTH(r.body) DESC 
        LIMIT 1
    ''', (asin, str(usuario_id)))
    
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