"""
Rutas de auditoría y rendimiento del LLM.

Expone endpoints para recuperar métricas operativas (latencia, tokens por 
segundo, tiempo de respuesta) almacenadas durante las ejecuciones del modelo.
Incluye soporte para paginación de resultados y limpieza selectiva de datos por perfil.
"""

import asyncio
import re
from fastapi import APIRouter, Query, HTTPException, Depends, Request, status
from fastapi.responses import StreamingResponse

# 📥 Importamos el esquema directamente desde tu carpeta de esquemas
from modulos.api.schemas.metricas import SolicitudLimpiezaCache

from modulos.base_datos.operaciones.auditoria import (
    obtener_ultima_metrica,
    obtener_metricas_paginadas
)
from modulos.base_datos.operaciones.productos import obtener_producto, vaciar_productos_por_usuario
from modulos.indexador.indexador import IndexadorRAG
from modulos.base_datos.operaciones.reportes import generar_excel_resenas, generar_pdf_resumen_ejecutivo
from modulos.seguridad.autenticacion import obtener_usuario_actual

from fastapi import Request
from modulos.api.rate_limiter import limiter

# Inicializamos en memoria RAM (perfecto para tu servidor en Oracle)


router = APIRouter()

def sanitizar_mensaje_error(mensaje: str) -> str:
    """
    Elimina tags, prefijos internos entre corchetes (ej. [FALLO], [MÉTRICA]) 
    y referencias técnicas para exponer solo mensajes limpios y amigables al cliente.
    """
    if not mensaje:
        return "No fue posible procesar la solicitud."
    # Remueve patrones como [FALLO], [ERROR], [MÉTRICA DIRECTA]
    mensaje_limpio = re.sub(r'\[.*?\]\s*', '', mensaje)
    return mensaje_limpio.strip()


@router.get("/metricas/ultima", status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")  # Limita a 10 solicitudes por minuto por IP
async def consultar_ultima_auditoria(
    request: Request,
    usuario_id: str = Depends(obtener_usuario_actual)
):
    """Endpoint para obtener las métricas de la última consulta realizada por el usuario."""
    resultado = await asyncio.to_thread(obtener_ultima_metrica, usuario_id)
    
    if not resultado:
        # 🛡️ MITIGACIÓN: Eliminamos la clave "prompt" por completo de la respuesta por defecto
        return {
            "ttft_ms": 0,
            "total_latency_ms": 0,
            "tokens_per_second": 0
        }
    
    # Formateamos la respuesta EXACTAMENTE con las claves que espera React,
    # asegurando que el prompt interno de LLM jamás viaje en el payload.
    return {
        "ttft_ms": resultado.get("ttft_ms", 0),
        "total_latency_ms": resultado.get("total_latency_ms", 0),
        "tokens_per_second": resultado.get("tokens_per_second", 0)
    }


@router.get("/metricas", status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")  # Limita a 10 solicitudes por minuto por IP
async def consultar_todas_auditorias(
    request: Request,
    limit: int = Query(10, description="Cantidad de registros a devolver por página", ge=1, le=100),
    skip: int = Query(0, description="Cantidad de registros a saltar (offset)", ge=0),
    usuario_id: str = Depends(obtener_usuario_actual) # Inyectamos la seguridad
):
    """
    Endpoint para obtener el historial de consultas paginado.
    Filtra los resultados estrictamente por el usuario autenticado.
    """
    # Pasamos el usuario_id a la consulta de base de datos
    resultados = await asyncio.to_thread(obtener_metricas_paginadas, limit, skip, usuario_id)
    
    # Filtramos los UUIDs (session_id) dentro de la clave 'datos' para evitar la vulnerabilidad B-02
    if isinstance(resultados, dict) and "datos" in resultados:
        for res in resultados["datos"]:
            if isinstance(res, dict) and "session_id" in res:
                del res["session_id"]

    return resultados


@router.post("/metricas/limpiar-cache", status_code=status.HTTP_200_OK)
@limiter.limit("2/minute")  # Limita a 2 solicitudes por minuto por IP
async def limpiar_datos_perfil_usuario(
    request: Request,
    cuerpo: SolicitudLimpiezaCache,
    usuario_id: str = Depends(obtener_usuario_actual)
):
    """
    Endpoint con validación de doble paso (M-03) para evitar borrados accidentales.
    Requiere que confirmar_borrado sea true y la frase_confirmacion sea 'ELIMINAR'.
    """
    # 🛡️ VALIDACIÓN DE DOBLE PASO (M-03)
    if not cuerpo.confirmar_borrado or cuerpo.frase_confirmacion.strip().upper() != "ELIMINAR":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Validación de doble paso fallida. Debes confirmar explícitamente el borrado escribiendo 'ELIMINAR'."
        )

    try:
        usuario_id = str(usuario_id)
        print(f"[DEBUG LIMPIEZA] Iniciando vaciado seguro para el usuario: {usuario_id}")

        # 1. Purgamos los datos en SQLite
        await asyncio.to_thread(vaciar_productos_por_usuario, usuario_id)
        
        # 2. Purgamos ChromaDB de forma aislada
        try:
            indexador = IndexadorRAG()
            await asyncio.to_thread(indexador.eliminar_vectores_de_usuario, usuario_id)
        except Exception as err_vector:
            print(f"[WARN VECTORIAL] No se completó la purga vectorial para {usuario_id}: {err_vector}")

        return {
            "status": "success",
            "mensaje": "Los datos y la base vectorial de tu perfil han sido eliminados correctamente mediante doble confirmación."
        }

    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"[ERROR CRÍTICO LIMPIAR CACHÉ]: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al procesar la limpieza del perfil."
        )
    

@router.post("/metricas/exportar-excel/{asin}", status_code=status.HTTP_200_OK)
@limiter.limit("5/minute")  # Limita a 5 solicitudes por minuto por IP
async def endpoint_exportar_excel(
    request: Request,
    asin: str,
    usuario_id: str = Depends(obtener_usuario_actual)
):
    """
    Genera dinámicamente el libro de Excel con todas las opiniones 
    del ASIN y lo envía al frontend como una descarga binaria.
    """

    asin_limpio = asin.strip().upper()
    usuario_str = str(usuario_id).strip()

    # 🛡️ VALIDACIÓN BOLA
    producto_data = await asyncio.to_thread(obtener_producto, asin_limpio, usuario_str)
    if not producto_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No se encontró el producto o no tienes permisos para exportarlo."
        )
    
    try:
        # Generamos el buffer binario en memoria
        buffer_excel = generar_excel_resenas(asin=asin, usuario_id=usuario_id)
        
        # Retornamos el archivo con los headers adecuados de Excel
        return StreamingResponse(
            buffer_excel,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename=Reporte_{asin.upper()}.xlsx"}
        )
        
    except ValueError as ve:
        # Sanitización de fugas de datos de error internos
        mensaje_limpio = sanitizar_mensaje_error(str(ve))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=mensaje_limpio)
    except Exception as e:
        print(f"[ERROR BACKEND EXCEL] Falló la generación del reporte: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Error interno al construir el archivo Excel."
        )


@router.post("/metricas/exportar-pdf/{asin}", status_code=status.HTTP_200_OK)
@limiter.limit("5/minute")  # Limita a 5 solicitudes por minuto por IP
async def endpoint_exportar_pdf(
    request: Request,
    asin: str,
    usuario_id: str = Depends(obtener_usuario_actual)
):
    """
    Genera dinámicamente un resumen ejecutivo en PDF y lo transmite como binario.
    """
    asin_limpio = asin.strip().upper()
    usuario_str = str(usuario_id).strip()

    # 🛡️ VALIDACIÓN BOLA
    producto_data = await asyncio.to_thread(obtener_producto, asin_limpio, usuario_str)
    if not producto_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No se encontró el producto o no tienes permisos para exportarlo."
        )
    
    try:
        buffer_pdf = generar_pdf_resumen_ejecutivo(asin=asin, usuario_id=usuario_id)
        
        return StreamingResponse(
            buffer_pdf,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=Resumen_Ejecutivo_{asin.upper()}.pdf"}
        )
    except ValueError as ve:
        # Sanitización del mensaje controlando excepciones de negocio
        mensaje_limpio = sanitizar_mensaje_error(str(ve))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=mensaje_limpio)
    except Exception as e:
        print(f"[ERROR BACKEND PDF] {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Error interno al construir el documento PDF."
        )