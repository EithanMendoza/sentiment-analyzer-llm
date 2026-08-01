"""
Rutas de gestión de sesiones de usuario.

Proporciona los endpoints protegidos para listar, consultar y eliminar
el historial de conversaciones de un usuario específico, verificando 
los permisos mediante su token de acceso.
"""

import asyncio
from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel
from typing import Optional

# Importamos las operaciones directas a la base de datos (añadiendo obtener_detalles_sesion y crear_sesion)
from modulos.base_datos.operaciones.sesiones import (
    obtener_sesiones_por_usuario,
    obtener_mensajes_por_sesion,
    eliminar_sesion_db,
    obtener_detalles_sesion,
    eliminar_todas_las_sesiones_del_usuario,
    crear_sesion
)
from modulos.base_datos.operaciones.productos import obtener_producto

# Importamos el guardia que decodifica el JWT
from modulos.seguridad.autenticacion import obtener_usuario_actual

from fastapi import Request
from main import limiter

router = APIRouter()

class SolicitudCrearSesion(BaseModel):
    asin: str
    titulo: Optional[str] = None


@router.post("/sesiones", status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")  # Limita a 5 solicitudes por minuto por IP
async def crear_sesion_endpoint(
    request: Request,
    solicitud: SolicitudCrearSesion,
    usuario_id: str = Depends(obtener_usuario_actual)
):
    """
    Crea una sesión de chat nueva y explícita para un producto ya analizado.
    Se usa desde 'Chat nuevo' cuando el usuario elige retomar un producto
    que ya fue analizado antes (aunque no tenga ningún chat activo todavía).
    """
    try:
        titulo = solicitud.titulo
        
        # 1. Validamos que el producto realmente exista en la BD antes de crear la sesión
        if not titulo:
            producto = obtener_producto(solicitud.asin)
            
            # Si el producto no existe, devolvemos un 404 controlado
            if not producto:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, 
                    detail="El ASIN proporcionado no existe en los registros."
                )
                
            nombre = producto["nombre"]
            titulo = f"Análisis de {nombre[:25]}..."

        # 2. Intentamos crear la sesión
        sesion_id = crear_sesion(usuario_id=usuario_id, asin=solicitud.asin, titulo=titulo)
        
        # Cambiamos el 500 por un 400 controlado para evitar fugas de información
        if not sesion_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail="No se pudo crear la sesión. Verifica los datos enviados."
            )

        return {"id": sesion_id, "asin": solicitud.asin, "titulo": titulo}

    except HTTPException as he:
        # Re-lanzamos las excepciones controladas que nosotros mismos definimos arriba (404, 400)
        raise he
    except Exception as e:
        # 3. Atrapamos errores crudos (ej. caída de BD o form-urlencoded erróneo)
        print(f"⚠️ [SEGURIDAD - ERROR INTERNO EN /sesiones] {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Error al procesar la solicitud. Formato inválido o error interno."
        )


@router.get("/sesiones")
@limiter.limit("10/minute")  # Limita a 10 solicitudes por minuto por IP
async def listar_sesiones(
    request: Request,
    usuario_id: str = Depends(obtener_usuario_actual)
):
    """
    Devuelve la lista de conversaciones (sesiones) pertenecientes al usuario autenticado.
    Ahora incluye automáticamente el campo 'asin' en cada sesión devuelta.
    """
    sesiones = await asyncio.to_thread(obtener_sesiones_por_usuario, usuario_id)
    return {"sesiones": sesiones}


@router.get("/sesiones/{sesion_id}/mensajes")
@limiter.limit("15/minute")  # Limita a 15 solicitudes por minuto por IP
async def obtener_historial_chat(
    request: Request,
    sesion_id: str,
    usuario_id: str = Depends(obtener_usuario_actual)
):
    """
    Devuelve todos los mensajes de una sesión específica, junto con los metadatos
    del producto (ASIN) para que el frontend pueda construir la interfaz gráfica.
    """
    # 1. Primero, obtenemos los detalles de la sesión para extraer el ASIN
    detalles = await asyncio.to_thread(obtener_detalles_sesion, sesion_id)
    
    # Validamos que la sesión exista y que el dueño sea el usuario que hace la petición
    if not detalles or detalles["usuario_id"] != usuario_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="La sesión no existe o no tienes permisos para verla."
        )
        
    # 2. Si la sesión es válida, extraemos los mensajes
    mensajes = await asyncio.to_thread(obtener_mensajes_por_sesion, sesion_id, usuario_id)
    
    # 3. Devolvemos el paquete completo para React
    return {
        "sesion_id": sesion_id, 
        "asin": detalles["asin"],       # <- ¡Crucial para tu UI!
        "titulo": detalles["titulo"],
        "mensajes": mensajes
    }


@router.delete("/sesiones/{sesion_id}")
@limiter.limit("5/minute")  # Limita a 5 solicitudes por minuto por IP
async def borrar_conversacion(
    request: Request,
    sesion_id: str,
    usuario_id: str = Depends(obtener_usuario_actual)
):
    """
    Elimina una sesión y (por CASCADE en SQLite) todos sus mensajes asociados.
    """
    exito = await asyncio.to_thread(eliminar_sesion_db, sesion_id, usuario_id)
    
    if not exito:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="La sesión no existe o no tienes permisos para eliminarla."
        )
        
    return {"estado": "ok", "mensaje": f"Sesión {sesion_id} eliminada correctamente."}

@router.delete("/usuarios/{usuario_id}/historial/purgar")
@limiter.limit("2/minute")  # Limita a 2 solicitudes por minuto por IP
async def purgar_historial_usuario(
    request: Request,
    usuario_id: str,
    usuario_autenticado: str = Depends(obtener_usuario_actual)
):
    """
    Purga el historial completo del usuario validando que coincida con el token de sesión.
    """
    # 1. Validación de seguridad: el usuario solo puede borrar su propio historial
    if usuario_id != usuario_autenticado:
        raise HTTPException(
            status_code=403, 
            detail="No tienes permisos para purgar el historial de otro usuario."
        )
        
    # 2. Eliminación en la base de datos SQLite
    exito = await asyncio.to_thread(eliminar_todas_las_sesiones_del_usuario, usuario_id)
    if not exito:
        raise HTTPException(
            status_code=500, 
            detail="Error al purgar el historial de conversaciones en la base de datos."
        )
        
    return {
        "status": "success",
        "mensaje": f"Historial purgado exitosamente para el usuario {usuario_id}."
    }