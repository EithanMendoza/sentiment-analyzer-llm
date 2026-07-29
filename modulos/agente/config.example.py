# config.example.py
# IMPORTANTE: Copia este archivo, renómbralo a 'config.py' y ajusta los 
# valores según el hardware de tu máquina. NO subas tu config.py a Git.

import os

RUTA_DB = os.path.join("datos", "base_vectorial")
COLECCION_DB = "reviews_analizadas"
MODELO_LLM = "qwen2.5:3b-instruct"
MODELO_EMBEDDING = "nomic-embed-text"

CONFIG_LLM = {
    "temperature": 0.0,         
    "request_timeout": 120.0, # Ajustar: 60s PC rápida, 600s Servidor   
    "additional_kwargs": {
        "num_thread": 4,      # Ajustar: Usa los núcleos de tu PC (Servidor usa 2)
        "num_ctx": 4096,        
        "top_k": 1,             
        "top_p": 0.1,           
        "repeat_penalty": 1.15
    }
}

SIMILARITY_TOP_K = 10         # Ajustar: 5 en servidor, 20 en PC potente