"""
Módulo: modelos.py
Responsabilidad: Inicializar y configurar los modelos de inteligencia artificial 
(LLM de Ollama y Modelo de Embeddings) aplicando los parámetros de hardware definidos 
en la configuración y registrándolos de forma global en el entorno de LlamaIndex.
"""

from llama_index.core import Settings
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.llms.ollama import Ollama
from .config import MODELO_LLM, MODELO_EMBEDDING, CONFIG_LLM

def configurar_modelos():
    """Configura y registra los modelos en el entorno global de LlamaIndex."""
    print("[INFO] Cargando modelo de embedding en memoria...")
    embed_model = OllamaEmbedding(model_name=MODELO_EMBEDDING)
    
    print(f"[INFO] Configurando LLM {MODELO_LLM} con restricciones de hardware...")
    llm = Ollama(
        model=MODELO_LLM,
        temperature=CONFIG_LLM["temperature"],
        request_timeout=CONFIG_LLM["request_timeout"],
        additional_kwargs=CONFIG_LLM["additional_kwargs"]
    )
    
    # Asignación global para LlamaIndex
    Settings.llm = llm
    Settings.embed_model = embed_model
    
    return llm, embed_model