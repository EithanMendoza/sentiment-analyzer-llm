"""
Rutas del motor de inferencia RAG.

Expone el endpoint principal de consulta conectado a LlamaIndex/ChromaDB.
Se encarga de procesar la entrada del usuario, generar la respuesta en 
streaming, y delegar el guardado del historial y las métricas de rendimiento.
"""

import time
import asyncio
from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import StreamingResponse

# 1. Esquema
from modulos.api.schemas.chat import PeticionMensaje

# 2. Operaciones de base de datos (Añadimos obtener_detalles_sesion)
from modulos.base_datos.operaciones.sesiones import guardar_mensaje, obtener_detalles_sesion
from modulos.base_datos.operaciones.auditoria import guardar_registro_auditoria

# 3. Guardia de seguridad
from modulos.seguridad.autenticacion import obtener_usuario_actual

router = APIRouter()

@router.post("/consultar")
async def hacer_consulta(
    peticion: PeticionMensaje, 
    request: Request,
    usuario_id: str = Depends(obtener_usuario_actual)
):
    """
    Endpoint principal de inferencia RAG.
    Genera la respuesta en streaming, guarda el historial y registra métricas de rendimiento.
    """
    # 1. Extraemos el motor RAG de la memoria global de FastAPI
    motor_ia = getattr(request.app.state, "motor_ia", None)
    if motor_ia is None:
        raise HTTPException(status_code=500, detail="El motor de IA no está disponible.")
    
    if not peticion.mensaje.strip():
        raise HTTPException(status_code=400, detail="La pregunta no puede estar vacía.")

    if not peticion.id_sesion:
        raise HTTPException(status_code=400, detail="Se requiere un id_sesion válido para chatear sobre un producto.")

    session_id = peticion.id_sesion.strip()

    # 2. RECUPERAMOS EL ASIN DE LA BASE DE DATOS (La pieza clave para la llave foránea)
    detalles_sesion = await asyncio.to_thread(obtener_detalles_sesion, session_id)
    if not detalles_sesion:
        raise HTTPException(status_code=404, detail="Sesión no encontrada. Asegúrate de que el producto haya sido analizado primero.")
    
    asin_real = detalles_sesion["asin"]

    # 3. Guardamos la pregunta del usuario inyectando el ASIN real
    await asyncio.to_thread(
        guardar_mensaje, 
        session_id, 
        'user', 
        peticion.mensaje, 
        asin_real, 
        usuario_id
    )

    try:
        # 4. Iniciar la consulta al motor RAG filtrando por ASIN
        tiempo_inicio = time.time()
        respuesta_stream = motor_ia.consultar(peticion.mensaje, asin_producto=asin_real)

        # 5. Generador asíncrono para el streaming y recolección de métricas
        async def generador_tokens():
            tiempo_primer_token = None
            conteo_tokens = 0
            buffer_respuesta = ""

            try:
                # Extraemos tokens del generador de LlamaIndex
                for token in respuesta_stream.response_gen:
                    if tiempo_primer_token is None:
                        tiempo_primer_token = time.time()
                    
                    buffer_respuesta += token
                    conteo_tokens += 1
                    yield token
                    
                # 6. Al terminar, guardamos la respuesta de la IA en la BD con su ASIN
                if buffer_respuesta.strip():
                    await asyncio.to_thread(
                        guardar_mensaje, 
                        session_id, 
                        'assistant', 
                        buffer_respuesta, 
                        asin_real, 
                        usuario_id
                    )
                    
                    # 7. Calculamos las métricas para la tabla de auditoría
                    tiempo_fin = time.time()
                    ttft_ms = (tiempo_primer_token - tiempo_inicio) * 1000 if tiempo_primer_token else 0.0
                    total_latency_ms = (tiempo_fin - tiempo_inicio) * 1000
                    tiempo_gen_activa = tiempo_fin - tiempo_primer_token if tiempo_primer_token else 0.0
                    tps = (conteo_tokens / tiempo_gen_activa) if tiempo_gen_activa > 0 else 0.0

                    await asyncio.to_thread(
                        guardar_registro_auditoria,
                        session_id=session_id,
                        user_prompt=peticion.mensaje,
                        system_response=buffer_respuesta,
                        ttft_ms=round(ttft_ms, 2),
                        total_latency_ms=round(total_latency_ms, 2),
                        tokens_per_second=round(tps, 2),
                        was_blocked=False,
                        tools_executed=[]
                    )
            except Exception as e:
                yield f"\n[Error durante el streaming: {str(e)}]"
                
        # 8. Retornamos la respuesta enviando el ID de sesión en los headers
        return StreamingResponse(
            generador_tokens(), 
            media_type="text/plain", 
            headers={"X-Session-ID": session_id}
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error durante la inferencia: {str(e)}")