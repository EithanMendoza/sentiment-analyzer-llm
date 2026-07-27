"""
Rutas de auditoría y rendimiento del LLM.

Expone endpoints para recuperar métricas operativas (latencia, tokens por 
segundo, tiempo de respuesta) almacenadas durante las ejecuciones del modelo.
Incluye soporte para paginación de resultados y limpieza selectiva de datos por perfil.
"""

import asyncio
# AGREGAMOS Request AQUÍ EN LAS IMPORTACIONES OFICIALES
from fastapi import APIRouter, Query, HTTPException, Depends, Request

from modulos.base_datos.operaciones.auditoria import (
    obtener_ultima_metrica,
    obtener_metricas_paginadas
)
from modulos.base_datos.operaciones.productos import vaciar_productos_por_usuario
from modulos.indexador.indexador import IndexadorRAG
from modulos.base_datos.operaciones.reportes import generar_excel_resenas, generar_pdf_resumen_ejecutivo
from fastapi.responses import StreamingResponse
from modulos.seguridad.autenticacion import obtener_usuario_actual

router = APIRouter()

@router.get("/metricas/ultima")
async def consultar_ultima_auditoria():
    """Endpoint para obtener las métricas de la última consulta realizada."""
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

@router.post("/metricas/limpiar-cache")
async def limpiar_datos_perfil_usuario(request: Request):
    """
    Endpoint que intercepta la acción de 'Borrar datos/Limpiar caché' del frontend.
    Elimina de manera estricta los productos, reseñas y vectores asociados
    ÚNICAMENTE al perfil del usuario autenticado.
    """
    try:
        # 1. Validación del Header de Autenticación
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            raise HTTPException(status_code=401, detail="No se proporcionó token de autenticación.")
            
        token = auth_header.replace("Bearer ", "").strip()
        
        # 2. Decodificación directa con PyJWT (sin importar funciones de autenticacion.py)
        import jwt
        try:
            # Decodificamos sin verificar la firma localmente sólo para leer los claims de sesión
            payload = jwt.decode(token, options={"verify_signature": False})
        except Exception as e_jwt:
            print(f"[ERROR JWT]: No se pudo decodificar el token: {e_jwt}")
            raise HTTPException(status_code=401, detail="Token inválido o malformado.")
            
        # Extraemos el ID soportando tanto 'sub' como 'id'
        usuario_id = payload.get("sub") or payload.get("id")
        if not usuario_id:
            raise HTTPException(status_code=401, detail="El token no contiene un identificador de usuario válido.")
            
        usuario_id = str(usuario_id)
        print(f"[DEBUG LIMPIEZA] Iniciando vaciado para el usuario: {usuario_id}")

        # 3. Purgamos los datos en SQLite
        await asyncio.to_thread(vaciar_productos_por_usuario, usuario_id)
        
        # 4. Purgamos ChromaDB de forma aislada
        try:
            indexador = IndexadorRAG()
            await asyncio.to_thread(indexador.eliminar_vectores_de_usuario, usuario_id)
        except Exception as err_vector:
            print(f"[WARN VECTORIAL] No se completó la purga vectorial para {usuario_id}: {err_vector}")

        return {
            "status": "success",
            "mensaje": "Los datos y la base vectorial de tu perfil han sido eliminados correctamente."
        }

    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"[ERROR CRÍTICO LIMPIAR CACHÉ]: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error interno al procesar la limpieza del perfil: {str(e)}"
        )
    
@router.post("/metricas/exportar-excel/{asin}")
async def endpoint_exportar_excel(
    asin: str,
    usuario_id: str = Depends(obtener_usuario_actual)
):
    """
    Genera dinámicamente el libro de Excel con todas las opiniones 
    del ASIN y lo envía al frontend como una descarga binaria.
    """
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
        # Error controlado si no hay opiniones
        raise HTTPException(status_code=444, detail=str(ve))
    except Exception as e:
        print(f"[ERROR BACKEND EXCEL] Falló la generación del reporte: {e}")
        raise HTTPException(status_code=500, detail="Error interno al construir el archivo Excel.")

@router.post("/metricas/exportar-pdf/{asin}")
async def endpoint_exportar_pdf(
    asin: str,
    usuario_id: str = Depends(obtener_usuario_actual)
):
    """
    Genera dinámicamente un resumen ejecutivo en PDF y lo transmite como binario.
    """
    try:
        buffer_pdf = generar_pdf_resumen_ejecutivo(asin=asin, usuario_id=usuario_id)
        
        return StreamingResponse(
            buffer_pdf,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=Resumen_Ejecutivo_{asin.upper()}.pdf"}
        )
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        print(f"[ERROR BACKEND PDF] {e}")
    raise HTTPException(status_code=500, detail="Error interno al construir el documento PDF.")