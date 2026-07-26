from fastapi import FastAPI, HTTPException, Depends
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware

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
        # Lo guardamos en el estado global para que chat.py pueda acceder a él
        app.state.motor_ia = motor_ia 
        print("[INFO] Motor inicializado correctamente.")
    except Exception as e:
        print(f"[ERROR FATAL] No se pudo inicializar el motor: {e}")
        app.state.motor_ia = None
        
    yield # Aquí el servidor se queda corriendo y escuchando peticiones
    
    print("\n[SHUTDOWN] Apagando el servidor y liberando recursos.")
    app.state.motor_ia = None


# Inicializamos la aplicación FastAPI
app = FastAPI(
    title="API del Agente Analítico de Reseñas",
    description="API modular con Streaming para consultar opiniones de productos.",
    version="1.0.0",
    lifespan=ciclo_vida_api
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
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
    tags=["Métricas y Monitoreo"], 
    dependencies=guardia_global
)



# =====================================================================
# ENDPOINT DE SALUD (Healthcheck)
# =====================================================================
@app.get("/estado", tags=["Sistema"])
async def verificar_estado():
    """Verifica si el servidor está arriba y si el motor RAG cargó bien."""
    motor_cargado = getattr(app.state, "motor_ia", None) is not None
    return {
        "estado": "en_linea",
        "motor_cargado": motor_cargado
    }