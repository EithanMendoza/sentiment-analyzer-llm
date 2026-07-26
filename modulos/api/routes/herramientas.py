"""
Rutas para las métricas, diagnósticos y herramientas de exportación.
"""
import os
import glob
import asyncio
from fastapi import APIRouter, HTTPException,Depends, status
from fastapi.responses import FileResponse
from modulos.seguridad.autenticacion import obtener_usuario_actual

# Importamos las herramientas lógicas (Actualizadas para SQLite)
from modulos.base_datos.operaciones.herramientas import (
    obtener_diagnostico_sistema,
    #listar_archivos_reportes,
    #limpiar_cache_scraping,
    exportar_analisis_csv,
    calcular_promedio_estrellas,
    contar_sentimientos_totales,
    obtener_reseña_mas_critica
)

# Importamos la conexión central y las operaciones de productos
from modulos.base_datos.conexion import obtener_conexion
from modulos.base_datos.operaciones.productos import obtener_producto

# NOTA: La seguridad (Depends) y el prefijo (/api) ya se aplican en main.py
router = APIRouter()

@router.get("/metricas/diagnostico")
async def endpoint_diagnostico():
    """Devuelve el estado actual del servidor local."""
    resultado = await asyncio.to_thread(obtener_diagnostico_sistema)
    return {"estado": "ok", "mensaje": resultado}

# =====================================================================
# @router.get("/metricas/reportes")
# async def endpoint_listar_reportes():
#     """Lista todos los archivos generados en el servidor."""
#     resultado = await asyncio.to_thread(listar_archivos_reportes)
#     return {"estado": "ok", "mensaje": resultado}
# 
# @router.post("/metricas/limpiar-cache")
# async def endpoint_limpiar_cache():
#     """Purga los archivos temporales remanentes."""
#     resultado = await asyncio.to_thread(limpiar_cache_scraping)
#     if "[ERROR]" in resultado:
#         raise HTTPException(status_code=500, detail=resultado)
#     return {"estado": "ok", "mensaje": resultado}

@router.post("/metricas/exportar-csv/{asin}")
async def endpoint_exportar_csv(asin: str):
    """Genera el archivo CSV para un ASIN específico y envía los bytes al frontend."""
    resultado = await asyncio.to_thread(exportar_analisis_csv, asin)
    
    if "[ERROR]" in resultado or "[FALLO]" in resultado:
        raise HTTPException(status_code=400, detail=resultado)
    
    # Buscamos el CSV recién generado en el directorio de salida
    rutas_posibles = glob.glob(f"datos/procesados/{asin}_*.csv")
    
    if not rutas_posibles:
        raise HTTPException(status_code=404, detail="Se generó el CSV pero no se pudo localizar en el servidor.")
    
    # Obtenemos el archivo más nuevo
    archivo_reciente = max(rutas_posibles, key=os.path.getctime)
    
    return FileResponse(
        path=archivo_reciente, 
        filename=f"Analisis_Resenas_{asin}.csv",
        media_type="text/csv"
    )

@router.get("/metricas/resumen/{asin}")
async def endpoint_metricas_rapidas(
    asin: str, 
    usuario_id: str = Depends(obtener_usuario_actual)  # <-- INYECTAMOS LA SEGURIDAD AQUÍ
):
    """
    Devuelve un resumen estadístico consultando la base de datos relacional,
    filtrando los datos de forma estricta por el usuario autenticado.
    """
    
    # 1. Ejecutamos los cálculos asíncronos pasándole el usuario_id a cada función
    promedio = await asyncio.to_thread(calcular_promedio_estrellas, asin, usuario_id)
    sentimientos = await asyncio.to_thread(contar_sentimientos_totales, asin, usuario_id)
    critica = await asyncio.to_thread(obtener_reseña_mas_critica, asin, usuario_id)
    
    # 2. Extraemos el nombre oficial garantizando que el producto le pertenezca a este usuario
    producto_data = await asyncio.to_thread(obtener_producto, asin, usuario_id)
    producto_nombre = producto_data["nombre"] if producto_data else f"Producto Desconocido ({asin})"

    # 3. Retornamos todo listo y aislado para el Dashboard en React
    return {
        "producto": producto_nombre,
        "promedio_estrellas": promedio,
        "distribucion_sentimientos": sentimientos,
        "reseña_destacada": critica
    }

@router.get("/metricas/ultima")
async def obtener_ultima_metrica():
    """Obtiene la última métrica de rendimiento de la IA desde la tabla de auditoría."""
    try:
        def fetch_db():
            conn = obtener_conexion()
            c = conn.cursor()
            c.execute('''
                SELECT user_prompt, ttft_ms, total_latency_ms, tokens_per_second 
                FROM auditoria 
                ORDER BY timestamp DESC LIMIT 1
            ''')
            registro = c.fetchone()
            conn.close()
            return registro
            
        registro = await asyncio.to_thread(fetch_db)

        if not registro:
            raise HTTPException(status_code=404, detail="Sin registros de auditoría aún.")

        return {
            "prompt": registro[0],
            "ttft_ms": registro[1],
            "total_latency_ms": registro[2],
            "tokens_per_second": registro[3]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/metricas/ultimo-asin")
async def obtener_ultimo_asin():
    """Devuelve el ASIN del último producto guardado en la base de datos."""
    def fetch_ultimo():
        conn = obtener_conexion()
        c = conn.cursor()
        # Usamos rowid para obtener el último insertado
        c.execute('SELECT asin FROM productos ORDER BY rowid DESC LIMIT 1')
        fila = c.fetchone()
        conn.close()
        return fila[0] if fila else None
        
    ultimo_asin = await asyncio.to_thread(fetch_ultimo)
    if not ultimo_asin:
        raise HTTPException(status_code=404, detail="No hay productos en la base de datos.")
    return {"asin": ultimo_asin}