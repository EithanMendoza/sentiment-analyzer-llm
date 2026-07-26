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
        """Intenta conectarse a ChromaDB de forma segura."""
        try:
            self.index = obtener_indice_vectorial()
        except Exception as e:
            print("[INFO] Arranque en frío: No hay base vectorial aún. El motor esperará datos.")

    # NOTA: Usamos RAG Manual y astream_complete porque as_query_engine() de LlamaIndex sufre de 
    # "Fake Streaming" bloqueando la CPU al usar modelos locales. 
    # ¡NO REFACTORIZAR a as_query_engine!
    
    async def consultar(self, pregunta: str, asin_producto: str = None, nombre_producto: str = None, caracteristicas: str = None):
        """Punto de entrada RAG Manual con Streaming 100% Nativo."""
        
        # 1. Intentamos cargar el índice vectorial si no existe
        if not self.index:
            self._intentar_cargar_motor()
            
        if not self.index:
            return MockStreamingResponse()

        # 2. BÚSQUEDA VECTORIAL (Retriever puro)
        retriever = self.index.as_retriever(similarity_top_k=SIMILARITY_TOP_K)
        nodos = await retriever.aretrieve(pregunta)
        
        # Extraemos solo el texto de las reseñas encontradas
        contexto_opiniones = "\n\n".join([nodo.node.text for nodo in nodos])

        # 3. ARMAMOS EL SÚPER-PROMPT MANUALMENTE
        prompt_final = (
            f"Eres un analista de reseñas de productos. Sé directo y conciso.\n"
            f"Responde a la consulta basándote ÚNICAMENTE en este contexto:\n"
            f"---------------------\n"
            f"[DATOS OFICIALES DEL PRODUCTO]\n"
            f"Nombre Oficial: {nombre_producto if nombre_producto else 'No disponible'}\n"
            f"ASIN: {asin_producto if asin_producto else 'No disponible'}\n"
            f"Características Técnicas:\n{caracteristicas if caracteristicas else 'No disponible'}\n\n"
            f"=== OPINIONES DE CLIENTES RECUPERADAS ===\n"
            f"{contexto_opiniones}\n"
            f"---------------------\n"
            f"REGLAS CRÍTICAS:\n"
            f"1. CERO CRUCE DE DATOS: Cada bloque de reseña es independiente.\n"
            f"2. ATRIBUCIÓN ESTRICTA: El texto pertenece a su autor.\n"
            f"3. NOMBRES VÁLIDOS: Nombres genéricos como 'Cliente Amazon', 'Anónimo' o apodos son nombres válidos. Úsalos tal cual aparecen.\n"
            f"4. NO ASUMAS NADA: Si el texto no menciona el tipo de producto, no lo inventes.\n"
            f"5. CLÁUSULA DE ESCAPE: Si la información no está, di: 'No cuento con registros suficientes en las opiniones.'\n\n"
            f"Consulta del usuario: {pregunta}\n"
            f"Respuesta:"
        )

        # 4. STREAMING DIRECTO AL LLM
        # astream_complete garantiza que Ollama devuelva chunk por chunk
        generador_nativo = await Settings.llm.astream_complete(prompt_final)
        return generador_nativo

# Bloque de prueba local (Actualizado para asyncio)
if __name__ == "__main__":
    async def prueba_local():
        motor = MotorAnaliticoLineal()
        print("\n--- PRUEBA DE VELOCIDAD Y CONTEXTO ---")
        asin_ejemplo = "B0CYWFH5Y9"
        pregunta_usuario = "¿Qué dicen las reseñas sobre la duración de la batería?"
        
        resultado = await motor.consultar(pregunta=pregunta_usuario, asin_producto=asin_ejemplo)
        
        print("\nRespuesta de la IA:")
        async for chunk in resultado:
            # Soportamos tanto la prueba mock como la respuesta real
            texto = chunk.delta if hasattr(chunk, 'delta') else chunk
            print(texto, end="", flush=True)
        print()

    # Ejecutar el loop asíncrono para la prueba
    asyncio.run(prueba_local())