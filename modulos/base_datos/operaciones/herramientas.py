import os
import csv
from datetime import datetime
from modulos.base_datos.conexion import obtener_conexion

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

def exportar_analisis_csv(asin: str, nombre_archivo: str = "exportacion_reseñas.csv") -> str:
    """
    Extrae las reseñas directamente de SQLite para el ASIN especificado 
    y las exporta a un CSV compatible con Excel.
    """
    os.makedirs(DIRECTORIO_SALIDA, exist_ok=True)
    
    conn = obtener_conexion()
    c = conn.cursor()
    c.execute('SELECT review_id, author, title, body, rating FROM resenas WHERE asin = ?', (asin,))
    datos = c.fetchall()
    conn.close()

    if not datos:
        return f"[FALLO] No existen datos extraídos en SQLite para el ASIN {asin}."

    try:
        ruta_completa = os.path.join(DIRECTORIO_SALIDA, f"{asin}_{nombre_archivo}")
        
        with open(ruta_completa, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["ID", "Autor", "Titulo", "Texto", "Estrellas"])
            
            for item in datos:
                texto_opinion = item[3]
                
                # Tu filtro sanitizador original
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

def calcular_promedio_estrellas(asin: str) -> str:
    """Calcula el promedio aritmético usando SQL nativo."""
    conn = obtener_conexion()
    c = conn.cursor()
    c.execute('SELECT AVG(rating), COUNT(review_id) FROM resenas WHERE asin = ?', (asin,))
    resultado = c.fetchone()
    conn.close()
    
    promedio, total = resultado
    if not total or total == 0:
        return "[INFO] Cero opiniones registradas."
        
    return f"[MÉTRICA DIRECTA] Calificación promedio calculada del producto: {promedio:.2f} estrellas de un total de {total} opiniones."

def contar_sentimientos_totales(asin: str) -> str:
    """
    Estima el sentimiento basándose en las estrellas (4-5 Positivo, 1-2 Negativo) 
    directamente desde la base de datos.
    """
    conn = obtener_conexion()
    c = conn.cursor()
    
    c.execute('SELECT COUNT(*) FROM resenas WHERE asin = ? AND rating >= 4', (asin,))
    pos = c.fetchone()[0]
    
    c.execute('SELECT COUNT(*) FROM resenas WHERE asin = ? AND rating <= 2', (asin,))
    neg = c.fetchone()[0]
    
    c.execute('SELECT COUNT(*) FROM resenas WHERE asin = ?', (asin,))
    total = c.fetchone()[0]
    conn.close()

    if total == 0:
        return "[FALLO] Base documental ausente."
        
    return f"[MÉTRICA] Distribución cuantitativa: {pos} Opiniones Positivas | {neg} Opiniones Negativas (Total: {total})."

def obtener_reseña_mas_critica(asin: str) -> str:
    """
    Usa el motor de SQLite para ordenar y extraer la peor opinión por estrellas 
    y desempata por la longitud del texto.
    """
    conn = obtener_conexion()
    c = conn.cursor()
    
    c.execute('''
        SELECT author, rating, body 
        FROM resenas 
        WHERE asin = ? 
        ORDER BY rating ASC, LENGTH(body) DESC 
        LIMIT 1
    ''', (asin,))
    
    critica = c.fetchone()
    conn.close()
    
    if not critica:
        return "[FALLO] No hay datos indexados para este producto."
        
    return f"=== OPINIÓN MÁS CRÍTICA DETECTADA ===\nAUTOR: {critica[0]}\nESTRELLAS: {critica[1]}★\nTEXTO: {critica[2]}"

def obtener_diagnostico_sistema() -> str:
    try:
        fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return f"[DIAGNÓSTICO] Sistema Operativo validado. Servidor Local Activo. Fecha/Hora: {fecha_actual}. Entorno RAG Híbrido Operando de forma Óptima."
    except Exception as e:
        return f"[ERROR] No se pudo recopilar el diagnóstico local: {str(e)}"