import os
import re
from fastapi import APIRouter, BackgroundTasks, HTTPException, status, Depends

# 1. Esquema propio
from modulos.api.schemas.scraping import SolicitudScraping

# 2. Operaciones de Base de Datos
from modulos.base_datos.operaciones.productos import (
    obtener_producto, 
    obtener_productos_por_usuario
)

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
        return {
            "status": "listo",
            "asin": asin,
            "mensaje": "Producto recuperado de la base de datos local del usuario."
        }

    # === VÍA LENTA: Scraping Nuevo ===
    api_token_apify = os.getenv("APIFY_TOKEN")
    if not api_token_apify:
        raise HTTPException(
            status_code=500, 
            detail="El token de Apify no está configurado en el servidor."
        )

    # Solo bloqueamos si ese ASIN específico se está procesando actualmente
    if estados_tareas.get(asin) == "procesando":
        return {
            "status": "procesando",
            "asin": asin,
            "mensaje": "Este producto ya está siendo extraído activamente."
        }

    # Marcamos explícitamente el estado como procesando
    estados_tareas[asin] = "procesando"

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
    Consulta el estado del proceso sin crear sesiones o historiales de chat automáticamente.
    """
    estado_actual = estados_tareas.get(asin, "no_encontrado")
    
    return {
        "asin": asin,
        "estado": estado_actual
    }