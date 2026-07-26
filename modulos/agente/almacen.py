"""
Módulo: almacen.py
Responsabilidad: Administrar la persistencia, conexión y recuperación de datos 
desde la base de datos vectorial (ChromaDB), encapsulando la lógica de acceso 
a los embeddings almacenados en disco.
"""

import os
import chromadb
from llama_index.core import VectorStoreIndex
from llama_index.vector_stores.chroma import ChromaVectorStore
from .config import RUTA_DB, COLECCION_DB

def obtener_indice_vectorial():
    """Conecta con ChromaDB y retorna el índice vectorial listo para consultas."""
    if not os.path.exists(RUTA_DB):
        raise FileNotFoundError(f"[ERROR] No se encontró la BD vectorial en '{RUTA_DB}'.")

    print("[INFO] Conectando a ChromaDB...")
    db_cliente = chromadb.PersistentClient(path=RUTA_DB)
    
    # CAMBIO CRUCIAL: Usamos get_or_create_collection para evitar que falle 
    # si la colección aún no fue consultada o indexada en este ciclo.
    chroma_collection = db_cliente.get_or_create_collection(
        name=COLECCION_DB,
        metadata={"hnsw:space": "cosine"}
    )
    
    vector_store = ChromaVectorStore(chroma_collection=chroma_collection)
    return VectorStoreIndex.from_vector_store(vector_store)