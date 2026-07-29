import os
import re
import asyncio
from fastapi import APIRouter, BackgroundTasks, HTTPException, status, Depends, Request

# 1. Esquema propio
from modulos.api.schemas.scraping import SolicitudScraping

# 2. Operaciones de Base de Datos y Conexión
from modulos.base_datos.operaciones.productos import obtener_productos_por_usuario
from modulos.base_datos.conexion import obtener_conexion

# 3. Importamos el orquestador completo
from modulos.orquestador import ControladorRAG, estados_tareas

# 4. Guardia de seguridad y Rate Limiting
from modulos.seguridad.autenticacion import obtener_usuario_actual
from slowapi import Limiter
from slowapi.util import get_remote_address

router = APIRouter()
orquestador = ControladorRAG()

# Inicializamos el limitador de tasa local mapeando la IP del cliente remoto
limiter = Limiter(key_func=get_remote_address)


def extraer_asin_de_url(texto: str) -> str:
    """Extrae el ASIN (10 caracteres) de un enlace o texto plano, previniendo SSRF."""
    texto = texto.strip()
    
    # 1. Caso A: Es un ASIN puro de 10 caracteres
    if len(texto) == 10 and texto.isalnum():
        return texto.upper()
    
    # 2. Caso B: Es una URL. Aplicamos Whitelisting estricto para bloquear SSRF
    # Solo permite protocolos seguros/estándar y dominios oficiales de Amazon (ej. amazon.com, amazon.es, amazon.com.mx)
    patron_dominio_seguro = r'^https?://(?:[a-zA-Z0-9-]+\.)*amazon\.[a-z]{2,3}(?:\.[a-z]{2})?/'
    
    if not re.match(patron_dominio_seguro, texto):
        # Si el dominio es una IP (como 169.254.x.x), localhost, o un dominio malicioso, se descarta aquí mismo
        return None
    
    # 3. Extraemos el ASIN únicamente de URLs validadas
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
    productos = await asyncio.to_thread(obtener_productos_por_usuario, usuario_id)
    return {"productos": productos}


@router.post("/scraper/iniciar", status_code=202)
@limiter.limit("5/minute")
async def iniciar_scraping(
    request: Request,  # 👈 Requerido internamente por SlowAPI de forma transparente para el frontend
    solicitud: SolicitudScraping, 
    tareas_fondo: BackgroundTasks,
    usuario_id: str = Depends(obtener_usuario_actual)
):
    """
    Recibe la URL o ASIN, revisa si existen reseñas reales registradas para este usuario (Vía Rápida),
    o lanza el scraping profundo y vectorización en segundo plano amarrado al usuario_id.
    Protegido con límite de tasa a 5 ejecuciones por minuto.
    """
    asin = extraer_asin_de_url(solicitud.url_o_asin)
    if not asin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se pudo encontrar un ASIN válido en el enlace proporcionado."
        )

    asin_limpio = asin.upper()
    usuario_str = str(usuario_id).strip()

    # === VÍA RÁPIDA: Se valida aislamiento multiusuario estricto sin fallbacks compartidos ===
    def verificar_resenas_existentes(asin_target: str, uid: str) -> bool:
        conn = obtener_conexion()
        c = conn.cursor()
        c.execute('''
            SELECT COUNT(*) FROM resenas r
            JOIN productos p ON UPPER(TRIM(r.asin)) = UPPER(TRIM(p.asin))
            WHERE UPPER(TRIM(r.asin)) = ? AND p.usuario_id = ?
        ''', (asin_target, uid))
        total = c.fetchone()[0]
        conn.close()
        return total > 0

    tiene_resenas = await asyncio.to_thread(verificar_resenas_existentes, asin_limpio, usuario_str)

    if tiene_resenas:
        estados_tareas[asin_limpio] = "completado"
        return {
            "status": "listo",
            "asin": asin_limpio,
            "mensaje": "Producto y reseñas cargados desde la base de datos local del usuario."
        }

    # === VÍA LENTA: Scraping Nuevo ===
    api_token_apify = os.getenv("APIFY_TOKEN")
    if not api_token_apify:
        raise HTTPException(
            status_code=500, 
            detail="El token de Apify no está configurado en el servidor."
        )

    # Solo bloqueamos si ese ASIN específico se está procesando actualmente
    if estados_tareas.get(asin_limpio) == "procesando":
        return {
            "status": "procesando",
            "asin": asin_limpio,
            "mensaje": "Este producto ya está siendo extraído activamente."
        }

    # Marcamos el estado como procesando
    estados_tareas[asin_limpio] = "procesando"

    # Lanzamos el trabajo en background asignando el usuario_id legítimo
    tareas_fondo.add_task(
        orquestador.procesar_nuevo_producto, 
        asin_limpio, 
        solicitud.marketplace,
        usuario_str
    )

    return {
        "status": "procesando",
        "asin": asin_limpio,
        "mensaje": f"Scraping y vectorización iniciados en segundo plano para el ASIN {asin_limpio}."
    }


@router.get("/scraper/estado/{asin}")
async def consultar_estado_scraping(
    asin: str, 
    usuario_id: str = Depends(obtener_usuario_actual)
):
    """
    Consulta el estado del proceso devolviendo un mensaje amigable y descriptivo.
    """
    asin_limpio = asin.strip().upper()
    estado_actual = estados_tareas.get(asin_limpio, "no_encontrado")
    
    mensajes_estado = {
        "procesando": "Extrayendo ficha técnica y opiniones de Amazon...",
        "completado": "El producto y las opiniones se han procesado exitosamente.",
        "error_sin_resenas": "No se encontraron opiniones públicas para este producto.",
        "error": "No se pudo completar el análisis del producto. Revisa el enlace o intenta más tarde.",
        "no_encontrado": "El producto no está en cola de procesamiento."
    }
    
    return {
        "asin": asin_limpio,
        "estado": estado_actual,
        "mensaje": mensajes_estado.get(estado_actual, "Estado desconocido.")
    }