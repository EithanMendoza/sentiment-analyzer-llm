"""
Rutas para el control, monitorización y ejecución del módulo de Scraping.
Blindado contra ataques SSRF mediante desestructuración estricta de URLs.
"""
import json
import os
import re
import asyncio
from urllib.parse import urlparse
from fastapi import APIRouter, BackgroundTasks, HTTPException, status, Depends, Request
from fastapi.responses import StreamingResponse

# 1. Esquema propio
from modulos.api.schemas.scraping import SolicitudScraping

# 2. Operaciones de Base de Datos y Conexión
from modulos.base_datos.operaciones.productos import obtener_productos_por_usuario
from modulos.base_datos.conexion import obtener_conexion

# 3. Importamos el orquestador completo
from modulos.orquestador import ControladorRAG, estados_tareas

# 4. Guardia de seguridad y Rate Limiting
from modulos.seguridad.autenticacion import obtener_usuario_actual
from main import limiter

router = APIRouter()
orquestador = ControladorRAG()


def extraer_asin_de_url(texto: str) -> str:
    """
    Extrae el ASIN (10 caracteres alfanuméricos) de un enlace o texto plano.
    Implementa mitigación estricta contra SSRF desestructurando la URL de forma segura.
    """
    texto = texto.strip()
    
    # Caso A: Es un ASIN puro de 10 caracteres
    if len(texto) == 10 and texto.isalnum():
        return texto.upper()
    
    # Caso B: Procesamiento de URL defensivo
    try:
        # urlparse divide de forma nativa la URL impidiendo trucos de manipulación como 'user:pass@host'
        url_parseada = urlparse(texto)
        
        # Validamos obligatoriamente que el esquema sea web seguro
        if url_parseada.scheme not in ["http", "https"]:
            return None
            
        # Extraemos el hostname limpio purgado de credenciales inyectadas
        host = url_parseada.hostname
        if not host:
            return None
            
        host = host.lower()
        
        # Lista blanca estricta de dominios de confianza de Amazon
        # Evita inyecciones tipo 'amazon.com.attacker.com' validando anclas de fin de cadena ($) o punto (.)
        dominios_permitidos = [
            "amazon.com", "amazon.com.mx", "amazon.es", "amazon.ca", 
            "amazon.co.uk", "amazon.de", "amazon.fr", "amazon.it"
        ]
        
        # Comprobamos que el host termine exactamente en uno de nuestros dominios seguros
        es_dominio_valido = any(host == dom or host.endswith("." + dom) for dom in dominios_permitidos)
        if not es_dominio_valido:
            return None
            
        # 3. Extraemos el ASIN únicamente de la ruta de la URL previamente sanitizada
        match = re.search(r'/(?:dp|gp/product|product|customer-reviews|product-reviews)/([A-Z0-9]{10})', url_parseada.path, re.IGNORECASE)
        if match:
            return match.group(1).upper()
            
    except Exception as e:
        print(f"[SECURITY WARNING] Intento de parseo de URL maliciosa bloqueado: {e}")
        return None
        
    return None


@router.get("/productos")
@limiter.limit("10/minute")
async def listar_productos(
    request: Request,
    usuario_id: str = Depends(obtener_usuario_actual)
):
    """
    Devuelve ÚNICAMENTE los productos analizados por el usuario autenticado.
    """
    productos = await asyncio.to_thread(obtener_productos_por_usuario, usuario_id)
    return {"productos": productos}


@router.post("/scraper/iniciar", status_code=202)
@limiter.limit("5/minute")
async def iniciar_scraping(
    request: Request,
    solicitud: SolicitudScraping, 
    tareas_fondo: BackgroundTasks,
    usuario_id: str = Depends(obtener_usuario_actual)
):
    """
    Inicia la extracción profunda analizando la URL bajo parámetros de seguridad estrictos.
    Integra fallback multiusuario para evitar duplicidad de costos en tareas idénticas.
    """
    asin = extraer_asin_de_url(solicitud.url_o_asin)
    if not asin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se pudo encontrar un ASIN válido o la estructura de la URL no está permitida."
        )

    asin_limpio = asin.upper()
    usuario_str = str(usuario_id).strip()

    # === VÍA RÁPIDA: Aislamiento multiusuario con fallback controlado ===
    def verificar_resenas_existentes(asin_target: str, uid: str) -> bool:
        conn = obtener_conexion()
        c = conn.cursor()
        # Modificado para alinearse con el motor unificado de métricas
        c.execute('''
            SELECT COUNT(*) FROM resenas r
            JOIN productos p ON UPPER(TRIM(r.asin)) = UPPER(TRIM(p.asin))
            WHERE UPPER(TRIM(r.asin)) = ? AND (p.usuario_id = ? OR p.usuario_id = 'usuario_default')
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
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="El token de Apify no está configurado en el servidor."
        )

    if estados_tareas.get(asin_limpio) == "procesando":
        return {
            "status": "procesando",
            "asin": asin_limpio,
            "mensaje": "Este producto ya está siendo extraído activamente."
        }

    estados_tareas[asin_limpio] = "procesando"

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


@router.get("/scraper/estado/stream/{asin}")
@limiter.limit("10/minute")
async def estado_scraping_sse(
    request: Request,
    asin: str, 
    usuario_id: str = Depends(obtener_usuario_actual)
):
    """
    Endpoint SSE que empuja actualizaciones de estado en tiempo real.
    """
    asin_limpio = asin.strip().upper()

    mensajes_estado = {
        "procesando": "Extrayendo ficha técnica y opiniones de Amazon...",
        "completado": "El producto y las opiniones se han procesado exitosamente.",
        "error_sin_resenas": "No se encontraron opiniones públicas para este producto.",
        "error": "No se pudo completar el análisis del producto. Revisa el enlace o intenta más tarde.",
        "no_encontrado": "El producto no está en cola de procesamiento."
    }

    async def generador_estado():
        estado_anterior = None

        while True:
            if await request.is_disconnected():
                break

            estado_actual = estados_tareas.get(asin_limpio, "no_encontrado")
            
            if estado_actual != estado_anterior:
                respuesta = {
                    "asin": asin_limpio,
                    "estado": estado_actual,
                    "mensaje": mensajes_estado.get(estado_actual, "Estado desconocido.")
                }
                
                yield f"data: {json.dumps(respuesta)}\n\n"
                status_anterior = estado_actual

            if estado_actual in ["completado", "error", "error_sin_resenas", "no_encontrado"]:
                break
                
            await asyncio.sleep(2)

    return StreamingResponse(
        generador_estado(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )