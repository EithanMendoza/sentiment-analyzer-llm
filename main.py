import os
from urllib.parse import urlparse
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware

# --- INTEGRACIÓN DE RATE LIMITING (SLOWAPI) ---
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

# ✅ IMPORTAMOS EL LIMITER DESDE EL ARCHIVO NEUTRAL
from modulos.api.rate_limiter import limiter

# Importamos el motor
from modulos.agente.motor import MotorAnaliticoLineal
from modulos.seguridad.autenticacion import obtener_usuario_actual
from modulos.base_datos.tablas_setup import inicializar_base_datos
from modulos.base_datos.operaciones.sesiones_login import inicializar_tabla_sesiones_activas

# Importamos los routers modulares
from modulos.api.routes import chat, herramientas, metricas, auth, historial, scraping


async def ciclo_vida_api(app: FastAPI):
    """
    Se ejecuta al arrancar y apagar el servidor. 
    Ideal para cargar modelos pesados y preparar la base de datos.
    """
    print("[INFO] Verificando e inicializando tablas de la base de datos...")
    try:
        inicializar_base_datos()
        inicializar_tabla_sesiones_activas()
        print("[INFO] Base de datos relacional lista y blindada.")
    except Exception as e:
        print(f"[ERROR FATAL] No se pudo crear/verificar la base de datos: {e}")

    print("[INFO] Inicializando el Motor Analítico (Ollama + ChromaDB)...")
    try:
        motor_ia = MotorAnaliticoLineal()
        app.state.motor_ia = motor_ia 
        print("[INFO] Motor inicializado correctamente.")
    except Exception as e:
        print(f"[ERROR FATAL] No se pudo inicializar el motor: {e}")
        app.state.motor_ia = None
        
    yield 
    
    print("\n[SHUTDOWN] Apagando el servidor y liberando recursos.")
    app.state.motor_ia = None


# ✅ Leemos el entorno para decidir si exponemos la documentación de la API
ENTORNO = os.getenv("ENTORNO", "produccion").lower()

# Inicializamos la aplicación FastAPI
app = FastAPI(
    title="API del Agente Analítico de Reseñas",
    description="API modular con Streaming para consultar opiniones de productos.",
    version="1.0.0",
    lifespan=ciclo_vida_api,
    debug=False,
    # 🛡️ MITIGACIÓN: Desactivar la documentación pública en producción
    docs_url="/docs" if ENTORNO == "desarrollo" else None,
    redoc_url="/redoc" if ENTORNO == "desarrollo" else None,
    openapi_url="/openapi.json" if ENTORNO == "desarrollo" else None
)

# Registramos el limitador
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# ✅ REV-2026-R8-05 & REV-2026-R8-08: Middleware de Seguridad Global, CSRF y Content-Type
@app.middleware("http")
async def middleware_seguridad_global(request: Request, call_next):
    # 1. 🛡️ PROTECCIÓN CSRF MEDIANTE VALIDACIÓN DE ORIGIN / REFERER EN MÉTODOS MUTABLES
    if request.method in ["POST", "PUT", "PATCH", "DELETE"]:
        origin = request.headers.get("origin") or request.headers.get("referer")
        if origin:
            parsed_origin = urlparse(origin)
            netloc = parsed_origin.netloc
            # Validamos que provenga del frontend oficial o de entornos de desarrollo autorizados
            es_origen_valido = (
                netloc == "review-agent-frontend.onrender.com" or
                netloc.startswith("localhost") or
                netloc.startswith("127.0.0.1")
            )
            if not es_origen_valido:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Origen no permitido por políticas de seguridad CSRF."}
                )

    # 2. Validación estricta de Content-Type para peticiones que envían datos
    if request.method in ["POST", "PUT", "PATCH"]:
        content_type = request.headers.get("Content-Type", "")
        
        if not content_type.startswith("application/json") and \
           not content_type.startswith("multipart/form-data") and \
           not content_type.startswith("application/x-www-form-urlencoded"):
            return JSONResponse(
                status_code=400,
                content={"detail": "Formato de datos no soportado. Se requiere JSON o Form-Urlencoded."}
            )
            
    response = await call_next(request)
    
    # 3. Inyección de cabeceras de seguridad HTTP completas
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
    
    # CSP: Permite Swagger UI (jsdelivr) en desarrollo y restricciones frame-ancestors
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "img-src 'self' data: https://fastapi.tiangolo.com; "
        "frame-ancestors 'none';"
    )

    # Mitigación REV-2026-06 (Ocultar versión de Server)
    if "server" in response.headers:
        del response.headers["server"]
        
    response.headers["Server"] = "Agente-API"
    
    return response


# ✅ REV-2026-05: Manejador estricto para ocultar el esquema de Pydantic
@app.exception_handler(RequestValidationError)
async def ocultar_esquema_pydantic_handler(request: Request, exc: RequestValidationError):
    print(f"⚠️ [VALIDACIÓN 422] Error de entrada en {request.url.path}: {exc.errors()}")
    
    return JSONResponse(
        status_code=422,
        content={"detail": "Datos de entrada inválidos. Verifica el formato de la solicitud."}
    )


# ✅ REV-2026-04: Hardening de CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", 
        "http://127.0.0.1:5173",
        "https://review-agent-frontend.onrender.com"
    ],
    allow_origin_regex=r"^http://(?:localhost|127\.0\.0\.1):\d+$",
    allow_credentials=True, 
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"], 
    expose_headers=["X-Session-ID"]
)


# =====================================================================
# 1. RUTAS PÚBLICAS (Sin protección)
# =====================================================================
app.include_router(auth.router, prefix="/api/auth", tags=["Autenticación"])


# =====================================================================
# 2. RUTAS CON PROTECCIÓN INTERNA (Extraen el usuario_id en el endpoint)
# =====================================================================
app.include_router(chat.router, prefix="/api", tags=["Inferencia IA"])
app.include_router(historial.router, prefix="/api", tags=["Historial"])

# =====================================================================
# 3. RUTAS CON PROTECCIÓN GLOBAL (Envueltas directamente en el router)
# =====================================================================
guardia_global = [Depends(obtener_usuario_actual)]

app.include_router(
    metricas.router, 
    prefix="/api", 
    tags=["Métricas y Monitoreo"], 
    dependencies=guardia_global
)

app.include_router(
    scraping.router, 
    prefix="/api", 
    tags=["Scraping y Extracción"],
    dependencies=guardia_global
)

app.include_router(
    herramientas.router, 
    prefix="/api", 
    tags=["Herramientas"], 
    dependencies=guardia_global
)


# =====================================================================
# ENDPOINT DE SALUD (Healthcheck)
# =====================================================================
@app.get("/estado", tags=["Sistema"])
@limiter.limit("5/minute")
async def verificar_estado(
    request: Request,
    usuario_id: str = Depends(obtener_usuario_actual) 
):
    """Verifica si el servidor está arriba y si el motor RAG cargó bien (Protegido)."""
    motor_cargado = getattr(app.state, "motor_ia", None) is not None
    return {
        "estado": "en_linea",
        "motor_cargado": motor_cargado
    }