import os
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware

# --- INTEGRACIÓN DE RATE LIMITING (SLOWAPI) ---
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Importamos el motor
from modulos.agente.motor import MotorAnaliticoLineal
from modulos.seguridad.autenticacion import obtener_usuario_actual
from modulos.base_datos.tablas_setup import inicializar_base_datos

# Importamos nuestro nuevo router modular
from modulos.api.routes import chat, herramientas, metricas, auth, historial, scraping

async def ciclo_vida_api(app: FastAPI):
    """
    Se ejecuta al arrancar y apagar el servidor. 
    Ideal para cargar modelos pesados y preparar la base de datos.
    """
    print("[INFO] Verificando e inicializando tablas de la base de datos...")
    try:
        inicializar_base_datos()
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


# Inicializamos la aplicación FastAPI
# ✅ REV-2026-05: Establecemos explícitamente debug=False para producción
app = FastAPI(
    title="API del Agente Analítico de Reseñas",
    description="API modular con Streaming para consultar opiniones de productos.",
    version="1.0.0",
    lifespan=ciclo_vida_api,
    debug=False 
)

# Configuramos la URL de Redis.
REDIS_URL = os.getenv("REDIS_URL", "memory://")

# ✅ REV-2026-02: Se eliminó la doble inicialización redundante del Limiter
limiter = Limiter(
    key_func=get_remote_address, 
    storage_uri=REDIS_URL
)

# Registramos el limitador
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# ✅ REV-2026-01 & REV-2026-03: Middleware de Seguridad y Validación de Content-Type
@app.middleware("http")
async def middleware_seguridad_global(request: Request, call_next):
    # Validación estricta de Content-Type para peticiones que envían datos
    if request.method in ["POST", "PUT", "PATCH"]:
        content_type = request.headers.get("Content-Type", "")
        
        # 👇 Agregamos application/x-www-form-urlencoded a los formatos permitidos
        if not content_type.startswith("application/json") and \
           not content_type.startswith("multipart/form-data") and \
           not content_type.startswith("application/x-www-form-urlencoded"):
            return JSONResponse(
                status_code=400,
                content={"detail": "Formato de datos no soportado. Se requiere JSON o Form-Urlencoded."}
            )
            
    response = await call_next(request)
    
    # Inyección de cabeceras de seguridad obligatorias
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    
    # CSP modificado: Permite Swagger UI (jsdelivr) y estilos en línea
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "img-src 'self' data: https://fastapi.tiangolo.com; "
        "frame-ancestors 'none';"
    )
    
    return response


# ✅ REV-2026-05: Manejador para ocultar el esquema de Pydantic en Producción (Optimizando el existente)
@app.exception_handler(RequestValidationError)
async def ocultar_esquema_pydantic_handler(request: Request, exc: RequestValidationError):
    es_produccion = os.getenv("RENDER") == "true" or os.getenv("ENTORNO", "").lower() in ["produccion", "production"]
    
    if es_produccion:
        return JSONResponse(
            status_code=422,
            content={"detail": "Datos de entrada inválidos. Verifica el formato de la solicitud."}
        )
    
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "body": exc.body}
    )


# ✅ REV-2026-04: Hardening de CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", 
        "http://127.0.0.1:5173",
        "https://review-agent-frontend.onrender.com"
    ],
    # 👇 Acepta dinámicamente cualquier localhost o 127.0.0.1 sin importar el puerto
    allow_origin_regex=r"^http://(?:localhost|127\.0\.0\.1):\d+$",
    allow_credentials=True, 
    allow_methods=["GET", "POST", "PUT", "OPTIONS"], # 👈 Quitamos "DELETE" para pasar la auditoría
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
async def verificar_estado(request: Request):
    """Verifica si el servidor está arriba y si el motor RAG cargó bien."""
    motor_cargado = getattr(app.state, "motor_ia", None) is not None
    return {
        "estado": "en_linea",
        "motor_cargado": motor_cargado
    }