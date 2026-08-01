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

    def construir_indice(self, datos_estructurados: list, usuario_id: str = "desconocido"):
        """
        ================================================================================
        CAMBIO DE PARADIGMA V2 (Arquitectura Multi-Producto y Aislamiento Vectorial)
        ================================================================================
        Fase 2 (Actual): El sistema ahora escala para soportar múltiples productos 
        y múltiples usuarios simultáneamente sin colapsar ni mezclar información.
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
            
            # ================================================================================
            # MITIGACIÓN PII (DATA MASKING): Se elimina el campo 'AUTOR' del bloque de texto
            # principal para forzar el anonimato real a nivel de datos. El LLM jamás verá el nombre.
            # ================================================================================
            texto_estructurado = f"""
            === RESEÑA DE CLIENTE ===
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
                    # Mantenemos el autor aquí por integridad de metadatos del vector indexado, 
                    # pero aislamos al LLM de leerlo directamente en el cuerpo del texto.
                    "autor": str(item.get("autor", "Anónimo")),
                    "estrellas": str(estrellas_valor),
                    "fuente": str(item.get("fuente", "Desconocida")),
                    "sentimiento": str(metadatos_ia.get("sentimiento", "Neutral")),
                    "categoria": str(metadatos_ia.get("categoria", "General")),
                    "fecha": str(metadatos_ia.get("fecha_publicacion", "")),
                    "asin": str(item.get("asin", "desconocido")),
                    # Guardamos obligatoriamente el usuario que indexa esta reseña para el aislamiento Multi-tenant
                    "usuario_id": str(usuario_id)
                }
            )
            documentos_llamaindex.append(doc)

        print("[INFO] Inicializando ChromaDB localmente...")
        
        # 🛡️ SOLUCIÓN: Limpiamos el caché global del sistema para evitar conflictos de estancias en ChromaDB
        try:
            chromadb.api.client.SharedSystemClient.clear_system_cache()
        except Exception:
            pass

        db_cliente = chromadb.PersistentClient(
            path=self.ruta_db,
            settings=Settings(
                chroma_tenant="default_tenant",
                chroma_database="default_database",
                allow_reset=True
            )
        )
        
        chroma_collection = db_cliente.get_or_create_collection(
            name=self.nombre_coleccion,
            metadata={"hnsw:space": "cosine"}
        )
        
        vector_store = ChromaVectorStore(chroma_collection=chroma_collection)
        storage_context = StorageContext.from_defaults(vector_store=vector_store)

        print("[INFO] Generando embeddings e indexando en la Base de Datos Vectorial...")
        
        index = VectorStoreIndex.from_documents(
            documentos_llamaindex,
            storage_context=storage_context,
            embed_model=self.embed_model
        )
        
        print(f"[OK] Base de datos vectorial actualizada con éxito en la carpeta '{self.ruta_db}'.")
        return index

    def eliminar_vectores_de_usuario(self, usuario_id: str) -> bool:
        """
        Elimina en ChromaDB ÚNICAMENTE los datos vectoriales asociados a un usuario_id.
        Implementación auto-contenida para evitar errores de atributos faltantes.
        """
        try:
            # 🛡️ Limpiamos también el caché aquí por seguridad
            try:
                chromadb.api.client.SharedSystemClient.clear_system_cache()
            except Exception:
                pass

            db_cliente = chromadb.PersistentClient(
                path=self.ruta_db,
                settings=Settings(
                    chroma_tenant="default_tenant",
                    chroma_database="default_database",
                    allow_reset=True
                )
            )
            
            try:
                coleccion = db_cliente.get_collection(name=self.nombre_coleccion)
            except Exception:
                print(f"[VECTORIAL] La colección '{self.nombre_coleccion}' aún no existe o está vacía.")
                return True
            
            # Buscamos los registros usando la etiqueta del usuario_id
            registros = coleccion.get(where={"usuario_id": str(usuario_id)})
            ids_a_borrar = registros.get("ids", [])
            
            if ids_a_borrar:
                coleccion.delete(ids=ids_a_borrar)
                print(f"[VECTORIAL] Se eliminaron {len(ids_a_borrar)} vectores del usuario '{usuario_id}'.")
            else:
                print(f"[VECTORIAL] No se encontraron vectores asociados al usuario '{usuario_id}'.")
            
            return True
        except Exception as e:
            print(f"[ERROR VECTORIAL] Falló al eliminar vectores del usuario '{usuario_id}': {e}")
            return False