"""
Módulo: config.py
Responsabilidad: Centralizar la configuración global del sistema y los hiperparámetros 
de hardware. 

Este es el único archivo que los integrantes del equipo deben modificar para adaptar 
el consumo de recursos (hilos de CPU, memoria de contexto, etc.) según las 
especificaciones técnicas de su propia laptop.
"""

import os

# Rutas y Almacenamiento
RUTA_DB = os.path.join("datos", "base_vectorial")
COLECCION_DB = "reviews_analizadas"

# Modelos de Ollama
MODELO_LLM = "qwen2.5:3b-instruct"
MODELO_EMBEDDING = "nomic-embed-text"

# Hiperparámetros de Inferencia (Modificables según los componentes de cada laptop)
CONFIG_LLM = {
    "temperature": 0.0,         # Determinismo puro
    "request_timeout": 120.0,
    "additional_kwargs": {
        "num_thread": 2,          # Modificar según los núcleos disponibles (ej. 2, 4, 8)
        "num_ctx": 2048,          # Límite de contexto en RAM
        "top_k": 1,               # Token más probable
        "top_p": 0.1,             # Recorte de probabilidad
        "repeat_penalty": 1.15
    }
}

# Configuración del Motor RAG
SIMILARITY_TOP_K = 3            # Fragmentos recuperados por consulta