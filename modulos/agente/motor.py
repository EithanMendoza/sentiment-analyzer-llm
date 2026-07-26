"""
Módulo: motor.py
Responsabilidad: Orquestar los componentes del sistema (configuración, modelos y 
almacenamiento vectorial). Expone el método de consulta optimizado para la API de FastAPI
mediante RAG manual y streaming asíncrono puro.
"""

import asyncio
from .config import SIMILARITY_TOP_K
from .modelos import configurar_modelos
from .almacen import obtener_indice_vectorial
from llama_index.core import Settings
from llama_index.core.vector_stores import MetadataFilters, ExactMatchFilter

class MockChunk:
    """Simula el fragmento de texto ('delta') que devuelve Ollama nativamente."""
    def __init__(self, texto):
        self.delta = texto

class MockStreamingResponse:
    """Simula el formato de respuesta asíncrona de Ollama para arranques en frío."""
    async def __aiter__(self):
        yield MockChunk("El motor aún no tiene datos. Por favor, procesa un enlace de Amazon primero.")

class MotorAnaliticoLineal:
    """
    Motor RAG optimizado para inferencia en CPU.
    Implementa Lazy Loading para soportar arranques en frío (servidor vacío).
    """
    def __init__(self):
        configurar_modelos()
        self.index = None
        self._intentar_cargar_motor()

    def _intentar_cargar_motor(self):
        """Intenta conectarse a ChromaDB de forma segura y recarga si hay datos nuevos."""
        try:
            # Forzamos una nueva lectura del almacén vectorial en disco
            self.index = obtener_indice_vectorial()
        except Exception as e:
            self.index = None
            print("[INFO] Arranque en frío: No hay base vectorial aún. El motor esperará datos.")

    # NOTA: Usamos RAG Manual y astream_complete porque as_query_engine() de LlamaIndex sufre de 
    # "Fake Streaming" bloqueando la CPU al usar modelos locales. 
    # ¡NO REFACTORIZAR a as_query_engine!
    
    async def consultar(self, pregunta: str, asin_producto: str = None, nombre_producto: str = None, caracteristicas: str = None):
        """Punto de entrada RAG Manual con Streaming 100% Nativo y filtrado por ASIN."""
        
        # 1. Intentamos cargar el índice vectorial si no existe
        if not self.index:
            self._intentar_cargar_motor()
            
        if not self.index:
            return MockStreamingResponse()

        # 2. BÚSQUEDA VECTORIAL PURA CON FILTRADO POR CONTEXTO (ASIN)
        # Si se proporciona un ASIN, limitamos la búsqueda exclusivamente a las reseñas de ese producto
        filtros = None
        if asin_producto:
            filtros = MetadataFilters(
                filters=[ExactMatchFilter(key="asin", value=asin_producto)]
            )

        retriever = self.index.as_retriever(
            similarity_top_k=SIMILARITY_TOP_K,
            filters=filtros
        )
        
        nodos = await retriever.aretrieve(pregunta)
        
        # Extraemos solo el texto de las reseñas encontradas
        contexto_opiniones = "\n\n".join([nodo.node.text for nodo in nodos])

        # Si no encontró nada específico con los filtros, intentamos un respaldo sin filtros para no dejar vacío al LLM
        if not contexto_opiniones and asin_producto:
            print(f"[MOTOR] No se hallaron nodos exactos para el ASIN {asin_producto}. Intentando búsqueda global...")
            retriever_global = self.index.as_retriever(similarity_top_k=SIMILARITY_TOP_K)
            nodos = await retriever_global.aretrieve(pregunta)
            contexto_opiniones = "\n\n".join([nodo.node.text for nodo in nodos])

        # 3. ARMAMOS EL SÚPER-PROMPT MANUALMENTE (Optimizado para Qwen 3B)
        prompt_final = (
            f"### ROL:\n"
            f"Eres un analista experto de reseñas de comercio electrónico. Sé directo, conciso y profesional.\n\n"
            
            f"### CONTEXTO DEL PRODUCTO:\n"
            f"- **Nombre Oficial:** {nombre_producto if nombre_producto else 'No disponible'}\n"
            f"- **ASIN:** {asin_producto if asin_producto else 'No disponible'}\n"
            f"- **Características Técnicas:**\n{caracteristicas if caracteristicas else 'No disponible'}\n\n"
            
            f"### OPINIONES DE CLIENTES RECUPERADAS:\n"
            f"{contexto_opiniones if contexto_opiniones else 'No hay reseñas recuperadas para este contexto.'}\n\n"
            
            f"### REGLAS CRÍTICAS:\n"
            f"1. **CERO CRUCE DE DATOS:** Cada bloque de reseña es independiente. No mezcles experiencias de distintos compradores.\n"
            f"2. **ATRIBUCIÓN:** Si mencionas una opinión específica, di qué autor la escribió y con cuántas estrellas califcó.\n"
            f"3. **NOMBRES VÁLIDOS:** Nombres como 'Cliente Amazon', 'Anónimo' o apodos deben usarse tal cual aparecen.\n"
            f"4. **NO ASUMAS NADA:** Si los textos no mencionan un dato, está prohibido inventarlo.\n"
            f"5. **CLÁUSULA DE ESCAPE:** Si la respuesta a la consulta no se encuentra en el contexto proporcionado, responde exactamente: 'No cuento con registros suficientes en las opiniones.'\n\n"
            
            f"### CONSULTA DEL USUARIO:\n"
            f"{pregunta}\n\n"
            f"### RESPUESTA:"
        )

        # 4. STREAMING DIRECTO AL LLM
        # astream_complete garantiza que Ollama devuelva chunk por chunk de forma ligera
        generador_nativo = await Settings.llm.astream_complete(prompt_final)
        return generador_nativo

# Bloque de prueba local
if __name__ == "__main__":
    async def prueba_local():
        motor = MotorAnaliticoLineal()
        print("\n--- PRUEBA DE VELOCIDAD Y CONTEXTO ---")
        asin_ejemplo = "B0CYWFH5Y9"
        pregunta_usuario = "¿Qué tal sale en general este producto?"
        
        resultado = await motor.consultar(pregunta=pregunta_usuario, asin_producto=asin_ejemplo)
        
        print("\nRespuesta de la IA:")
        async for chunk in resultado:
            texto = chunk.delta if hasattr(chunk, 'delta') else chunk
            print(texto, end="", flush=True)
        print()

    asyncio.run(prueba_local())