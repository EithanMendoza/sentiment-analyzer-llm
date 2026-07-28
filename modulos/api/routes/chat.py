import time
import asyncio
from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import StreamingResponse

# 1. Esquema
from modulos.api.schemas.chat import PeticionMensaje

# 2. Operaciones de base de datos
from modulos.base_datos.operaciones.sesiones import guardar_mensaje, obtener_detalles_sesion
from modulos.base_datos.operaciones.auditoria import guardar_registro_auditoria
from modulos.base_datos.operaciones.productos import obtener_producto

# 3. Guardia de seguridad, Guardrails y Rate Limiting
from modulos.seguridad.autenticacion import obtener_usuario_actual
from modulos.seguridad.guardrails import validar_prompt_seguro
from slowapi import Limiter
from slowapi.util import get_remote_address

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


@router.post("/consultar")
@limiter.limit("20/minute")
async def hacer_consulta(
    peticion: PeticionMensaje, 
    request: Request,  # 👈 Utilizado tanto para SlowAPI como para extraer el estado del motor
    usuario_id: str = Depends(obtener_usuario_actual)
):
    """
    Endpoint principal de inferencia RAG.
    Genera la respuesta en streaming, guarda el historial y registra métricas de rendimiento.
    Protegido con un límite de 20 consultas por minuto.
    """
    # 1. Extraemos el motor RAG de la memoria global de FastAPI
    motor_ia = getattr(request.app.state, "motor_ia", None)
    if motor_ia is None:
        raise HTTPException(status_code=500, detail="El motor de IA no está disponible.")
    
    if not peticion.mensaje.strip():
        raise HTTPException(status_code=400, detail="La pregunta no puede estar vacía.")

    # Validamos el prompt con los guardrails de seguridad (Anti Prompt Injection)
    es_seguro, mensaje_error = validar_prompt_seguro(peticion.mensaje)
    if not es_seguro:
        raise HTTPException(status_code=400, detail=mensaje_error)

    if not peticion.id_sesion:
        raise HTTPException(status_code=400, detail="Se requiere un id_sesion válido para chatear sobre un producto.")

    session_id = peticion.id_sesion.strip()
    usuario_str = str(usuario_id).strip()

    # 2. RECUPERAMOS EL ASIN DE LA BASE DE DATOS Y VERIFICAMOS PROPIEDAD (Prevención IDOR)
    detalles_sesion = await asyncio.to_thread(obtener_detalles_sesion, session_id)
    if not detalles_sesion:
        raise HTTPException(status_code=404, detail="Sesión no encontrada. Asegúrate de que el producto haya sido analizado primero.")
    
    # Validación estricta de propiedad de la sesión
    id_dueno_sesion = detalles_sesion.get("usuario_id")
    if id_dueno_sesion and str(id_dueno_sesion).strip() != usuario_str:
        raise HTTPException(
            status_code=403, 
            detail="No tienes autorización para acceder a esta conversación."
        )

    asin_real = detalles_sesion["asin"]

    # Obtener datos del producto
    datos_producto = await asyncio.to_thread(obtener_producto, asin_real)

    if datos_producto and datos_producto.get("caracteristicas"):
        caracteristicas_lista = datos_producto["caracteristicas"]
        # Formateamos la lista de Python a texto legible con viñetas para la IA
        if isinstance(caracteristicas_lista, list):
            caracteristicas_texto = "\n- " + "\n- ".join(str(c) for c in caracteristicas_lista)
        else:
            caracteristicas_texto = str(caracteristicas_lista)
        nombre_prod = datos_producto["nombre"]
    else:
        caracteristicas_texto = "No hay especificaciones adicionales registradas."
        nombre_prod = detalles_sesion["titulo"]

    # 3. Guardamos la pregunta del usuario inyectando el ASIN real
    await asyncio.to_thread(
        guardar_mensaje, 
        session_id, 
        'user', 
        peticion.mensaje, 
        asin_real, 
        usuario_str
    )

    try:
        # 4. Iniciar la consulta al motor RAG filtrando por ASIN
        tiempo_inicio = time.time()
        respuesta_stream = await motor_ia.consultar(
            pregunta=peticion.mensaje, 
            asin_producto=asin_real,
            nombre_producto=nombre_prod,
            caracteristicas=caracteristicas_texto
        )

        # 5. Generador asíncrono modificado para SSE
        async def generador_tokens():
            tiempo_primer_token = None
            conteo_tokens = 0
            buffer_respuesta = ""

            try:
                async for chunk in respuesta_stream:
                    if tiempo_primer_token is None:
                        tiempo_primer_token = time.time()
                    
                    texto_fragmento = chunk.delta
                    buffer_respuesta += texto_fragmento
                    conteo_tokens += 1
                    
                    # 🔴 CAMBIO CRUCIAL 1: Formato estándar SSE
                    yield f"data: {texto_fragmento}\n\n"
                    
                # 6. Al terminar, guardamos la respuesta de la IA en la BD
                if buffer_respuesta.strip():
                    await asyncio.to_thread(
                        guardar_mensaje, 
                        session_id, 
                        'assistant', 
                        buffer_respuesta, 
                        asin_real, 
                        usuario_str
                    )
                    
                # ... (tu código de métricas se mantiene exactamente igual) ...

            except Exception as e:
                print(f"[ERROR STREAMING CHAT]: {e}")
                # Formato SSE también para los errores en el stream
                yield f"data: \n[Se produjo un error al procesar el resto de la respuesta.]\n\n"
                
        # 🔴 CAMBIO CRUCIAL 2: Headers y Media Type correctos
        return StreamingResponse(
            generador_tokens(), 
            media_type="text/event-stream", 
            headers={
                "X-Session-ID": session_id,
                "Cache-Control": "no-cache",
                "Connection": "keep-alive"
            }
        )

    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"[ERROR INFERENCIA CHAT]: {e}")
        raise HTTPException(
            status_code=500, 
            detail="Error interno al procesar la inferencia de la consulta."
        )