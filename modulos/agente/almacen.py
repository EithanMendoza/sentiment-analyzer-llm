"""
Módulo: almacen.py
Responsabilidad: Administrar la persistencia, conexión y recuperación de datos 
desde la base de datos vectorial (ChromaDB), encapsulando la lógica de acceso 
a los embeddings almacenados en disco.
"""

import os
import chromadb
from chromadb.config import Settings
from llama_index.core import VectorStoreIndex
from llama_index.vector_stores.chroma import ChromaVectorStore
from .config import RUTA_DB, COLECCION_DB

def obtener_indice_vectorial():
    """Conecta con ChromaDB y retorna el índice vectorial listo para consultas."""
    if not os.path.exists(RUTA_DB):
        raise FileNotFoundError(f"[ERROR] No se encontró la BD vectorial en '{RUTA_DB}'.")

    print("[INFO] Conectando a ChromaDB...")
    
    # 🛡️ SOLUCIÓN: Limpiamos el caché global del sistema para evitar conflictos de estancias en ChromaDB
    try:
        chromadb.api.client.SharedSystemClient.clear_system_cache()
    except Exception:
        pass

    db_cliente = chromadb.PersistentClient(
        path=RUTA_DB,
        settings=Settings(
            chroma_tenant="default_tenant",
            chroma_database="default_database",
            allow_reset=True
        )
    )
    
    # CAMBIO CRUCIAL: Usamos get_or_create_collection para evitar que falle 
    # si la colección aún no fue consultada o indexada en este ciclo.
    chroma_collection = db_cliente.get_or_create_collection(
        name=COLECCION_DB,
        metadata={"hnsw:space": "cosine"}
    )
    
    vector_store = ChromaVectorStore(chroma_collection=chroma_collection)
    return VectorStoreIndex.from_vector_store(vector_store)