import os
import re
from fastapi import APIRouter, BackgroundTasks, HTTPException, status, Depends

# 1. Esquema propio
from modulos.api.schemas.scraping import SolicitudScraping

# 2. Operaciones de Base de Datos (Importamos la función filtrada por usuario)
from modulos.base_datos.operaciones.productos import (
    obtener_producto, 
    obtener_productos_por_usuario
)
from modulos.base_datos.operaciones.sesiones import crear_sesion

# 3. Importamos el orquestador completo
from modulos.orquestador import ControladorRAG, estados_tareas

# 4. Guardia de seguridad
from modulos.seguridad.autenticacion import obtener_usuario_actual

router = APIRouter()
orquestador = ControladorRAG()


def extraer_asin_de_url(texto: str) -> str:
    """Extrae el ASIN (10 caracteres) de un enlace o texto plano."""
    texto = texto.strip()
    if len(texto) == 10 and texto.isalnum():
        return texto.upper()
    
    match = re.search(r'/(?:dp|gp/product|product|customer-reviews|product-reviews)/([A-Z0-9]{10})', texto)
    if match:
        return match.group(1).upper()
    return None


@router.get("/productos")
async def listar_productos(usuario_id: str = Depends(obtener_usuario_actual)):
    """
    Devuelve ÚNICAMENTE los productos analizados por el usuario autenticado.
    El frontend lo usa en 'Chat nuevo' para no mezclar productos de perfiles diferentes.
    """
    productos = obtener_productos_por_usuario(usuario_id)
    return {"productos": productos}


@router.post("/scraper/iniciar", status_code=202)
async def iniciar_scraping(
    solicitud: SolicitudScraping, 
    tareas_fondo: BackgroundTasks,
    usuario_id: str = Depends(obtener_usuario_actual)
):
    """
    Recibe la URL, extrae el ASIN, revisa si ya existe en SQLite para este usuario (Vía Rápida),
    o lanza el scraping profundo en segundo plano amarrado al usuario_id.
    """
    asin = extraer_asin_de_url(solicitud.url_o_asin)
    if not asin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se pudo encontrar un ASIN válido en el enlace proporcionado."
        )

    # === VÍA RÁPIDA: El producto ya fue analizado por este usuario ===
    producto_existente = obtener_producto(asin, usuario_id=usuario_id)
    if producto_existente:
        titulo = f"Análisis de {producto_existente['nombre'][:25]}..."
        sesion_id = crear_sesion(usuario_id=usuario_id, asin=asin, titulo=titulo)
        
        return {
            "status": "listo",
            "asin": asin,
            "sesion_id": sesion_id,
            "mensaje": "Producto recuperado de la base de datos local del usuario."
        }

    # === VÍA LENTA: Scraping Nuevo ===
    api_token_apify = os.getenv("APIFY_TOKEN")
    if not api_token_apify:
        raise HTTPException(
            status_code=500, 
            detail="El token de Apify no está configurado en el servidor."
        )

    # Evitamos duplicidad de trabajos
    if estados_tareas.get(asin) == "procesando":
        return {
            "status": "procesando",
            "asin": asin,
            "mensaje": "Este producto ya está siendo extraído."
        }

    # Lanzamos el trabajo en background asignando el usuario_id
    tareas_fondo.add_task(
        orquestador.procesar_nuevo_producto, 
        asin, 
        solicitud.marketplace,
        usuario_id
    )

    return {
        "status": "procesando",
        "asin": asin,
        "mensaje": f"Scraping y vectorización iniciados en segundo plano para el ASIN {asin}."
    }


@router.get("/scraper/estado/{asin}")
async def consultar_estado_scraping(
    asin: str, 
    usuario_id: str = Depends(obtener_usuario_actual)
):
    """
    Endpoint para que el frontend consulte el progreso. 
    Si ya terminó, genera la sesión automáticamente amarrada al usuario activo.
    """
    estado_actual = estados_tareas.get(asin, "no_encontrado")
    
    if estado_actual == "completado":
        # Creamos la sesión aislada para el usuario
        producto = obtener_producto(asin, usuario_id=usuario_id)
        nombre = producto["nombre"] if producto else f"Producto {asin}"
        titulo = f"Análisis de {nombre[:25]}..."
        
        sesion_id = crear_sesion(usuario_id=usuario_id, asin=asin, titulo=titulo)
        
        return {
            "estado": "completado",
            "asin": asin,
            "sesion_id": sesion_id
        }
        
    return {
        "asin": asin,
        "estado": estado_actual
    }