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
    crear_sesion
)
from modulos.base_datos.operaciones.productos import obtener_producto

# Importamos el guardia que decodifica el JWT
from modulos.seguridad.autenticacion import obtener_usuario_actual

router = APIRouter()


class SolicitudCrearSesion(BaseModel):
    asin: str
    titulo: Optional[str] = None


@router.post("/sesiones", status_code=status.HTTP_201_CREATED)
async def crear_sesion_endpoint(
    solicitud: SolicitudCrearSesion,
    usuario_id: str = Depends(obtener_usuario_actual)
):
    """
    Crea una sesión de chat nueva y explícita para un producto ya analizado.
    Se usa desde 'Chat nuevo' cuando el usuario elige retomar un producto
    que ya fue analizado antes (aunque no tenga ningún chat activo todavía).
    """
    titulo = solicitud.titulo
    if not titulo:
        producto = obtener_producto(solicitud.asin)
        nombre = producto["nombre"] if producto else f"Producto {solicitud.asin}"
        titulo = f"Análisis de {nombre[:25]}..."

    sesion_id = crear_sesion(usuario_id=usuario_id, asin=solicitud.asin, titulo=titulo)
    if not sesion_id:
        raise HTTPException(status_code=500, detail="No se pudo crear la sesión de chat.")

    return {"id": sesion_id, "asin": solicitud.asin, "titulo": titulo}


@router.get("/sesiones")
async def listar_sesiones(usuario_id: str = Depends(obtener_usuario_actual)):
    """
    Devuelve la lista de conversaciones (sesiones) pertenecientes al usuario autenticado.
    Ahora incluye automáticamente el campo 'asin' en cada sesión devuelta.
    """
    sesiones = await asyncio.to_thread(obtener_sesiones_por_usuario, usuario_id)
    return {"sesiones": sesiones}


@router.get("/sesiones/{sesion_id}/mensajes")
async def obtener_historial_chat(sesion_id: str, usuario_id: str = Depends(obtener_usuario_actual)):
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
async def borrar_conversacion(sesion_id: str, usuario_id: str = Depends(obtener_usuario_actual)):
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