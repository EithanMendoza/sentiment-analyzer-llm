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
MODELO_LLM = "qwen2.5:7b-instruct-q4_K_M"  # 🚀 Cambiado al modelo 7B optimizado que tienes descargado
MODELO_EMBEDDING = "nomic-embed-text"

# Hiperparámetros de Inferencia (Optimizados para tu servidor en Oracle Cloud de 12GB RAM)
CONFIG_LLM = {
    "temperature": 0.0,         # Determinismo puro
    "request_timeout": 120.0,
    "additional_kwargs": {
        "num_thread": 4,          # 🚀 Subido a 4 hilos para procesar más rápido en el CPU del servidor
        "num_ctx": 4096,          # 🚀 Duplicado a 4096 para que recuerde más contexto y más reseñas a la vez
        "top_k": 1,               # Token más probable
        "top_p": 0.1,             # Recorte de probabilidad
        "repeat_penalty": 1.15
    }
}

# Configuración del Motor RAG
SIMILARITY_TOP_K = 3            # Fragmentos recuperados por consulta