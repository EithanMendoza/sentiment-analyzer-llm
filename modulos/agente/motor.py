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
        
        print("\n" + "="*60)
        print(f"[MOTOR CONSULTA] 📩 Nueva petición recibida:")
        print(f"  ├─ Pregunta: '{pregunta}'")
        print(f"  ├─ ASIN: {asin_producto}")
        print(f"  └─ Producto: {nombre_producto}")

        # 1. VERIFICAMOS SI EL ÍNDICE ESTÁ CARGADO
        if self.index is None:
            print("[MOTOR DEBUG] 🔄 El índice no está en memoria. Intentando cargarlo...")
            try:
                self.index = obtener_indice_vectorial()
                if self.index:
                    print("[MOTOR DEBUG] ✅ Índice vectorial cargado exitosamente.")
            except Exception as e:
                self.index = None
                print(f"[MOTOR ERROR] ❌ Falló la recarga del índice vectorial: {e}")
            
        # Si definitivamente no hay índice en disco, devolvemos respuesta de arranque en frío
        if not self.index:
            print("[MOTOR ALERT] 🧊 Sin índice vectorial disponible. Devolviendo 'MockStreamingResponse' (Arranque en frío).")
            print("="*60 + "\n")
            return MockStreamingResponse()

        # 2. BÚSQUEDA VECTORIAL PURA CON FILTRADO POR CONTEXTO (ASIN)
        asin_normalizado = str(asin_producto).strip().upper() if asin_producto else None
        filtros = None
        if asin_producto:
            print(f"[MOTOR DEBUG] 🔍 Aplicando filtro de metadatos exacto para ASIN: '{asin_producto}'")
            filtros = MetadataFilters(
                filters=[ExactMatchFilter(key="asin", value=asin_producto)]
            )
        else:
            print("[MOTOR DEBUG] ⚠️ No se proporcionó ASIN. Realizando búsqueda global sin filtros.")

        retriever = self.index.as_retriever(
            similarity_top_k=SIMILARITY_TOP_K,
            filters=filtros
        )
        
        print("[MOTOR DEBUG] 🛰️ Ejecutando retriever.aretrieve()...")
        nodos = await retriever.aretrieve(pregunta)
        print(f"[MOTOR DEBUG] 📦 Nodos recuperados con filtro: {len(nodos)}")
        
        # Extraemos solo el texto de las reseñas encontradas
        contexto_opiniones = "\n\n".join([nodo.node.text for nodo in nodos])

        # Si no encontró nada específico con los filtros, intentamos un respaldo sin filtros
        if not contexto_opiniones and asin_producto:
            print(f"[MOTOR WARN] ⚠️ No se hallaron nodos exactos para el ASIN '{asin_producto}'. Intentando búsqueda global de respaldo...")
            retriever_global = self.index.as_retriever(similarity_top_k=SIMILARITY_TOP_K)
            nodos = await retriever_global.aretrieve(pregunta)
            contexto_opiniones = "\n\n".join([nodo.node.text for nodo in nodos])
            print(f"[MOTOR DEBUG] 📦 Nodos recuperados en búsqueda global: {len(nodos)}")

        print(f"[MOTOR DEBUG] 📝 Longitud total del texto de opiniones recuperado: {len(contexto_opiniones)} caracteres.")

        # 3. ARMAMOS EL SÚPER-PROMPT MANUALMENTE (Optimizado para Qwen 3B)
        prompt_final = (
    f"### SISTEMA\n"
    f"Eres una IA experta en analizar reseñas. No eres humano.\n"
    f"SALUDOS: Si el usuario solo saluda (ej. 'hola') o pregunta quién eres, responde EXACTAMENTE: "
    f"'¡Hola! Soy el Asistente Experto en analisis de reseñas. ¿En qué te ayudo con este producto?' y DETENTE.\n\n"
    
    f"### DATOS DEL PRODUCTO\n"
    f"- Nombre: {nombre_producto if nombre_producto else 'N/A'}\n"
    f"- ASIN: {asin_producto if asin_producto else 'N/A'}\n"
    f"- Ficha: {caracteristicas if caracteristicas else 'N/A'}\n"
    f"- Opiniones: {contexto_opiniones if contexto_opiniones else 'N/A'}\n\n"
    
    f"### TAREA PRINCIPAL Y RESTRICCIONES (NO LAS MENCIONES EN TU RESPUESTA)\n"
    f"- OBJETIVO: Tu prioridad es esforzarte en encontrar la respuesta a la consulta basándote en los DATOS DEL PRODUCTO.\n"
    f"- VE AL GRANO: Responde directamente la duda. NO repitas estas reglas ni expliques tu proceso lógico.\n"
    f"- CITA: Si mencionas una reseña, incluye el autor y sus estrellas.\n"
    f"- NO INVENTES: Usa exclusivamente la información de los datos proporcionados.\n"
    f"- ÚLTIMO RECURSO: ÚNICAMENTE si es absolutamente imposible responder porque la información no existe en los datos, di: 'No cuento con registros suficientes en las opiniones.'\n\n"
    
    f"### CONSULTA DEL USUARIO\n"
    f"{pregunta}\n\n"
    f"### RESPUESTA DIRECTA:\n"
)
        # 4. STREAMING DIRECTO AL LLM (Ollama / Qwen)
        print("[MOTOR DEBUG] 🚀 Enviando el prompt final a Ollama via Settings.llm.astream_complete()...")
        print("="*60 + "\n")
        
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