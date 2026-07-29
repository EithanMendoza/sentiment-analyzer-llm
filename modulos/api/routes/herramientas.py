"""
Rutas para las métricas, diagnósticos y herramientas de exportación.
"""
import os
import glob
import asyncio
from fastapi import APIRouter, HTTPException, Depends, status, Request
from fastapi.responses import FileResponse
from modulos.seguridad.autenticacion import obtener_usuario_actual

# Importamos las herramientas lógicas (Actualizadas para SQLite)
from modulos.base_datos.operaciones.herramientas import (
    obtener_diagnostico_sistema,
    exportar_analisis_csv,
    calcular_promedio_estrellas,
    contar_sentimientos_totales,
    obtener_reseña_mas_critica
)

# Importamos la conexión central y las operaciones de productos
from modulos.base_datos.conexion import obtener_conexion
from modulos.base_datos.operaciones.productos import obtener_producto

# Importamos el Rate Limiter
from slowapi import Limiter
from slowapi.util import get_remote_address

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


@router.get("/metricas/diagnostico")
@limiter.limit("5/minute")
async def endpoint_diagnostico(
    request: Request,
    usuario_id: str = Depends(obtener_usuario_actual)
):
    """Devuelve el estado actual del servidor local."""
    resultado = await asyncio.to_thread(obtener_diagnostico_sistema)
    return {"estado": "ok", "mensaje": resultado}


@router.post("/metricas/exportar-csv/{asin}")
@limiter.limit("5/minute")
async def endpoint_exportar_csv(
    request: Request,
    asin: str,
    usuario_id: str = Depends(obtener_usuario_actual)
):
    """Genera el archivo CSV para un ASIN específico y envía los bytes al frontend."""
    asin_limpio = asin.strip().upper()
    usuario_str = str(usuario_id).strip()

    # 1. Verificar que el producto exista y le pertenezca al usuario
    producto_data = await asyncio.to_thread(obtener_producto, asin_limpio, usuario_str)
    if not producto_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No se encontró el producto o no tienes permisos para exportar sus datos."
        )

    # 2. Exportar CSV pasándole AMBOS parámetros (asin y usuario_id)
    resultado = await asyncio.to_thread(exportar_analisis_csv, asin_limpio, usuario_str)
    
    # Sanitización de errores: No exponer tags internas al cliente
    if isinstance(resultado, str) and ("[ERROR]" in resultado or "[FALLO]" in resultado or "No existen" in resultado):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="No fue posible exportar el análisis en formato CSV."
        )
    
    # 3. Buscamos el CSV recién generado con el patrón que incluye el usuario_id
    rutas_posibles = glob.glob(f"datos/procesados/{usuario_str}_{asin_limpio}_*.csv")
    if not rutas_posibles:
        # Respaldo de búsqueda por si el nombre no lleva prefijo de usuario
        rutas_posibles = glob.glob(f"datos/procesados/*{asin_limpio}*.csv")
    
    if not rutas_posibles:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="El archivo CSV generado no fue localizado en el servidor."
        )
    
    # Obtenemos el archivo más reciente
    archivo_reciente = max(rutas_posibles, key=os.path.getctime)
    
    return FileResponse(
        path=archivo_reciente, 
        filename=f"Analisis_Resenas_{asin_limpio}.csv",
        media_type="text/csv"
    )

@router.get("/metricas/resumen/{asin}")
@limiter.limit("5/minute")
async def endpoint_metricas_rapidas(
    request: Request,
    asin: str, 
    usuario_id: str = Depends(obtener_usuario_actual)
):
    """
    Devuelve un resumen estadístico consultando la base de datos relacional,
    filtrando los datos de forma estricta por el usuario autenticado.
    """
    asin_limpio = asin.strip().upper()
    usuario_str = str(usuario_id).strip()

    # 1. Ejecutamos los cálculos asíncronos pasándole el usuario_id a cada función
    promedio = await asyncio.to_thread(calcular_promedio_estrellas, asin_limpio, usuario_str)
    sentimientos = await asyncio.to_thread(contar_sentimientos_totales, asin_limpio, usuario_str)
    critica = await asyncio.to_thread(obtener_reseña_mas_critica, asin_limpio, usuario_str)
    
    # 2. Extraemos el nombre oficial garantizando que el producto le pertenezca a este usuario
    producto_data = await asyncio.to_thread(obtener_producto, asin_limpio, usuario_str)
    producto_nombre = producto_data["nombre"] if producto_data else f"Producto ({asin_limpio})"

    # 3. Retornamos todo listo y aislado para el Dashboard en React
    return {
        "producto": producto_nombre,
        "promedio_estrellas": promedio,
        "distribucion_sentimientos": sentimientos,
        "reseña_destacada": critica
    }


@router.get("/metricas/ultima")
@limiter.limit("5/minute")
async def obtener_ultima_metrica(
    request: Request,
    usuario_id: str = Depends(obtener_usuario_actual)
):
    """Obtiene la última métrica de rendimiento de la IA del usuario autenticado desde auditoría."""
    try:
        usuario_str = str(usuario_id).strip()

        def fetch_db():
            conn = obtener_conexion()
            c = conn.cursor()
            c.execute('''
                SELECT user_prompt, ttft_ms, total_latency_ms, tokens_per_second 
                FROM auditoria a
                JOIN sesiones s ON a.session_id = s.id_sesion
                WHERE s.usuario_id = ?
                ORDER BY a.timestamp DESC LIMIT 1
            ''', (usuario_str,))
            registro = c.fetchone()
            conn.close()
            return registro
            
        registro = await asyncio.to_thread(fetch_db)

        if not registro:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sin registros de auditoría disponibles.")

        return {
            "prompt": registro[0],
            "ttft_ms": registro[1],
            "total_latency_ms": registro[2],
            "tokens_per_second": registro[3]
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"[ERROR METRICAS ULTIMA]: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error al recuperar métricas de auditoría.")


@router.get("/metricas/ultimo-asin")
@limiter.limit("5/minute")
async def obtener_ultimo_asin(
    request: Request,
    usuario_id: str = Depends(obtener_usuario_actual)
):
    """Devuelve el ASIN del último producto guardado por el usuario autenticado."""
    usuario_str = str(usuario_id).strip()

    def fetch_ultimo():
        conn = obtener_conexion()
        c = conn.cursor()
        c.execute('''
            SELECT asin FROM productos 
            WHERE usuario_id = ? 
            ORDER BY rowid DESC LIMIT 1
        ''', (usuario_str,))
        fila = c.fetchone()
        conn.close()
        return fila[0] if fila else None
        
    ultimo_asin = await asyncio.to_thread(fetch_ultimo)
    if not ultimo_asin:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No se encontraron productos registrados para el usuario.")
    
    return {"asin": ultimo_asin}