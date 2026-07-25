"""
Rutas de auditoría y rendimiento del LLM.

Expone endpoints para recuperar métricas operativas (latencia, tokens por 
segundo, tiempo de respuesta) almacenadas durante las ejecuciones del modelo.
Incluye soporte para paginación de resultados.
"""

import asyncio
from fastapi import APIRouter, Query, HTTPException

from modulos.base_datos.operaciones.auditoria import (
    obtener_ultima_metrica,
    obtener_metricas_paginadas
)

router = APIRouter()

@router.get("/metricas/ultima")
async def consultar_ultima_auditoria():
    """Endpoint para obtener las métricas de la última consulta realizada."""
    # Usamos asyncio.to_thread para no bloquear el Event Loop de FastAPI
    resultado = await asyncio.to_thread(obtener_ultima_metrica)
    
    if not resultado:
        raise HTTPException(status_code=404, detail="No hay registros de auditoría disponibles.")
        
    return resultado

@router.get("/metricas")
async def consultar_todas_auditorias(
    limit: int = Query(10, description="Cantidad de registros a devolver por página", ge=1, le=100),
    skip: int = Query(0, description="Cantidad de registros a saltar (offset)", ge=0)
):
    """
    Endpoint para obtener el historial de consultas paginado.
    Ideal para mostrar tablas de análisis de rendimiento en el frontend.
    """
    resultados = await asyncio.to_thread(obtener_metricas_paginadas, limit, skip)
    return resultados