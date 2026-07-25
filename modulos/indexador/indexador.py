import os
import chromadb
from chromadb.config import Settings
from llama_index.core import StorageContext, VectorStoreIndex
from llama_index.core.schema import Document
from llama_index.vector_stores.chroma import ChromaVectorStore
from llama_index.embeddings.ollama import OllamaEmbedding

class IndexadorRAG:
    def __init__(self, ruta_db="datos/base_vectorial", nombre_coleccion="reviews_analizadas"):
        self.ruta_db = ruta_db
        self.nombre_coleccion = nombre_coleccion
        
        # Configuramos el modelo de embeddings local de Ollama
        self.embed_model = OllamaEmbedding(model_name="nomic-embed-text")

    def construir_indice(self, datos_estructurados: list):
        """
        ================================================================================
        CAMBIO DE PARADIGMA V2 (Arquitectura Multi-Producto y Aislamiento Vectorial)
        ================================================================================
        Fase 1 (Previa): In-Memory Processing para evitar cuellos de botella de I/O.
        
        Fase 2 (Actual): El sistema ahora escala para soportar múltiples productos 
        simultáneamente sin colapsar ni mezclar información.
        1. Persistencia Acumulativa: Se eliminó `delete_collection`. Ahora usamos 
           `get_or_create_collection` para añadir vectores nuevos sin borrar el historial.
        2. Etiquetado Fuerte: Se inyecta obligatoriamente el `asin` en los metadatos 
           de cada fragmento (Document) para que ChromaDB lo indexe.
        3. Aislamiento Lógico: Gracias a esto, el motor de inferencia puede aplicar un 
           filtro estricto (where={"asin": ...}) aislando el contexto del LLM.
        ================================================================================
        """
        if not datos_estructurados:
            print("[ERROR] La lista de datos está vacía. No hay nada que indexar.")
            return None

        print(f"[INFO] Convirtiendo {len(datos_estructurados)} opiniones a nodos de LlamaIndex...")
        documentos_llamaindex = []

        for item in datos_estructurados:
            estrellas_valor = item.get("estrellas") if item.get("estrellas") else 0
            metadatos_ia = item.get("metadatos", {})
            
            # FORMATO BLINDADO CORREGIDO: Ahora el LLM sí "verá" la calificación y la fecha
            texto_estructurado = f"""
            === RESEÑA DE CLIENTE ===
            AUTOR: {item.get('autor', 'Anónimo')}
            CALIFICACIÓN: {estrellas_valor} de 5 estrellas
            FECHA: {metadatos_ia.get('fecha_publicacion', 'Fecha desconocida')}
            TITULO: {item.get('titulo_comentario', 'Sin título')}
            TEXTO DE LA OPINIÓN: {item.get('texto', '')}
            =========================
            """.strip()

            doc = Document(
                text=texto_estructurado,
                id_=str(item.get("id", "desconocido")),
                metadata={
                    "autor": str(item.get("autor", "Anónimo")),
                    "estrellas": str(estrellas_valor),
                    "fuente": str(item.get("fuente", "Desconocida")),
                    "sentimiento": str(metadatos_ia.get("sentimiento", "Neutral")),
                    "categoria": str(metadatos_ia.get("categoria", "General")),
                    "fecha": str(metadatos_ia.get("fecha_publicacion", "")),
                    # LA PIEZA CLAVE DE LA FASE 2:
                    "asin": str(metadatos_ia.get("asin", "desconocido"))
                }
            )
            documentos_llamaindex.append(doc)

        print("[INFO] Inicializando ChromaDB localmente...")
        # CONFIGURACIÓN EXPLÍCITA DE TENANT: Previene el bloqueo de hilos fantasmas en Windows
        db_cliente = chromadb.PersistentClient(
            path=self.ruta_db,
            settings=Settings(
                chroma_tenant="default_tenant",
                chroma_database="default_database",
                allow_reset=True
            )
        )
        
        # SOLUCIÓN PARA LA RÚBRICA: Forzamos la métrica de distancia a Similitud de Coseno ('cosine')
        # Utilizamos get_or_create_collection para mantener vivos los productos anteriores
        chroma_collection = db_cliente.get_or_create_collection(
            name=self.nombre_coleccion,
            metadata={"hnsw:space": "cosine"}
        )
        
        # Acoplamos ChromaDB como el almacén de vectores oficial de LlamaIndex 
        vector_store = ChromaVectorStore(chroma_collection=chroma_collection)
        storage_context = StorageContext.from_defaults(vector_store=vector_store)

        print("[INFO] Generando embeddings e indexando en la Base de Datos Vectorial...")
        
        # Construimos el índice pasando nuestros documentos, embeddings y el contexto de almacenamiento
        index = VectorStoreIndex.from_documents(
            documentos_llamaindex,
            storage_context=storage_context,
            embed_model=self.embed_model
        )
        
        print(f"[OK] Base de datos vectorial actualizada con éxito en la carpeta '{self.ruta_db}'.")
        return index