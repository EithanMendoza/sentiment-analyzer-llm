"""
Módulo: motor.py
Responsabilidad: Orquestar los componentes del sistema (configuración, modelos y 
almacenamiento vectorial). Expone el método de consulta optimizado para la API de FastAPI
mediante RAG manual y streaming asíncrono puro.
"""

import asyncio
import chromadb
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
    """Simula el formato de respuesta asíncrona de Ollama para arranques en frío o fallas."""
    def __init__(self, mensaje="El motor aún no tiene datos. Por favor, procesa un enlace de Amazon primero."):
        self.mensaje = mensaje

    async def __aiter__(self):
        yield MockChunk(self.mensaje)

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
            self.index = obtener_indice_vectorial()
        except Exception as e:
            self.index = None
            print(f"[INFO] Arranque en frío: No hay base vectorial aún ({e}). El motor esperará datos.")

    # NOTA: Usamos RAG Manual y astream_complete porque as_query_engine() de LlamaIndex sufre de 
    # "Fake Streaming" bloqueando la CPU al usar modelos locales. 
    # ¡NO REFACTORIZAR a as_query_engine!
    
    async def consultar(self, pregunta: str, asin_producto: str = None, nombre_producto: str = None, caracteristicas: str = None, usuario_id: str = None):
        """Punto de entrada RAG Manual con Streaming 100% Nativo y filtrado por ASIN."""
        
        print("\n" + "="*60)
        print(f"[MOTOR CONSULTA] 📩 Nueva petición recibida:")
        print(f"  ├─ Pregunta: '{pregunta}'")
        print(f"  ├─ ASIN: {asin_producto}")
        print(f"  └─ Producto: {nombre_producto}")

        # 1. SINCRONIZACIÓN Y OBTENCIÓN DEL ÍNDICE
        try:
            self.index = obtener_indice_vectorial()
            if self.index:
                print("[MOTOR DEBUG] ✅ Índice vectorial verificado y recargado exitosamente.")
        except Exception as e:
            self.index = None
            print(f"[MOTOR ERROR] ❌ Falló la recarga del índice vectorial: {e}")
            
        # Si definitivamente no hay índice en disco, devolvemos respuesta de arranque en frío
        if not self.index:
            print("[MOTOR ALERT] 🧊 Sin índice vectorial disponible. Devolviendo 'MockStreamingResponse'.")
            print("="*60 + "\n")
            return MockStreamingResponse()

        # 2. BÚSQUEDA VECTORIAL PURA CON FILTRADO POR CONTEXTO (ASIN)
       # 2. BÚSQUEDA VECTORIAL PURA CON FILTRADO ESTRICTO (ASIN + USUARIO)
        filtros_lista = []
        
        if asin_producto:
            # ✅ CORRECCIÓN: Normalizamos el ASIN para que ChromaDB no falle por diferencias de mayúsculas/minúsculas
            asin_normalizado = str(asin_producto).strip().upper()
            print(f"[MOTOR DEBUG] 🔍 Aplicando filtro de metadatos exacto para ASIN: '{asin_normalizado}'")
            filtros_lista.append(ExactMatchFilter(key="asin", value=asin_normalizado))
        else:
            print("[MOTOR DEBUG] ⚠️ No se proporcionó ASIN. Realizando búsqueda global sin filtros de ASIN.")

        if usuario_id:
            print(f"[MOTOR DEBUG] 🔒 Aplicando aislamiento vectorial estricto para el usuario: '{usuario_id}'")
            filtros_lista.append(ExactMatchFilter(key="usuario_id", value=str(usuario_id)))
        else:
            print("[MOTOR DEBUG] ⚠️ Advertencia: No se proporcionó usuario_id para el aislamiento vectorial.")

        # Construimos el objeto MetadataFilters combinando ambos filtros con un AND implícito
        filtros = MetadataFilters(filters=filtros_lista) if filtros_lista else None

        try:
            retriever = self.index.as_retriever(
                similarity_top_k=SIMILARITY_TOP_K,
                filters=filtros
            )
            
            print("[MOTOR DEBUG] 🛰️ Ejecutando retriever.aretrieve()...")
            nodos = await retriever.aretrieve(pregunta)
            print(f"[MOTOR DEBUG] 📦 Nodos recuperados con filtro estricto: {len(nodos)}")
            
            # Extraemos solo el texto de las reseñas encontradas
            contexto_opiniones = "\n\n".join([nodo.node.text for nodo in nodos])
            print(f"[MOTOR DEBUG] 📝 Longitud total del texto de opiniones recuperado: {len(contexto_opiniones)} caracteres.")
        except Exception as e:
            print(f"[MOTOR ERROR] ❌ Error durante la recuperación de nodos: {e}")
            contexto_opiniones = ""

        # 3. ARMAMOS EL SÚPER-PROMPT MANUALMENTE (Optimizado para Qwen 3B)
        nombre_seguro = nombre_producto if nombre_producto else 'No especificado'
        ficha_segura = caracteristicas if caracteristicas else 'Sin ficha técnica'
        opiniones_seguras = contexto_opiniones if contexto_opiniones else 'No hay opiniones registradas para esta consulta.'

        prompt_final = (
            f"Eres un analista experto en compras. Tu única tarea es responder a la pregunta del usuario basándote estrictamente en el contexto del producto proporcionado.\n\n"
            f"=== CONTEXTO DEL PRODUCTO ===\n"
            f"Producto: {nombre_seguro}\n"
            f"Características: {ficha_segura}\n"
            f"Opiniones de clientes:\n{opiniones_seguras}\n"
            f"=============================\n\n"
            f"REGLAS OBLIGATORIAS:\n"
            f"- Si el usuario dice 'hola' o te saluda, responde amablemente preguntando en qué le puedes ayudar.\n"
            f"- Responde a la pregunta de forma directa, natural y al grano.\n"
            f"- Utiliza SÓLO la información del bloque 'CONTEXTO DEL PRODUCTO'. No inventes datos.\n"
            f"- Cita las calificaciones (estrellas) cuando menciones una opinión, pero mantén al usuario anónimo.\n"
            f"- Si la pregunta no se puede responder con el contexto proporcionado, responde: 'Lo siento, no encuentro información sobre eso en las opiniones o características.'\n\n"
            f"Pregunta del usuario: {pregunta}\n\n"
            f"Respuesta:"
        )

        # 4. STREAMING DIRECTO AL LLM (Ollama / Qwen)
        print("[MOTOR DEBUG] 🚀 Enviando el prompt final a Ollama via Settings.llm.astream_complete()...")
        print("="*60 + "\n")
        
        try:
            generador_nativo = await Settings.llm.astream_complete(prompt_final)
            return generador_nativo
        except Exception as e:
            print(f"[MOTOR ERROR] ❌ Falló la generación en streaming: {e}")
            return MockStreamingResponse("Ocurrió un error temporal al conectar con el modelo de lenguaje. Inténtalo nuevamente.")

# Bloque de prueba local
if __name__ == "__main__":
    import time
    import sqlite3 # Importamos SQLite solo para la prueba autónoma
    import asyncio
    
    async def prueba_local():
        motor = MotorAnaliticoLineal()
        print("\n--- PRUEBA DE VELOCIDAD Y CONTEXTO ---")
        asin_ejemplo = "B0D44135S2"
        pregunta_usuario = "¿Por qué hay calificaciones de 1 estrella, qué fue lo que falló?"
        
        # 1. SIMULAMOS LO QUE HACE FASTAPI: Buscar el producto en la BD real
        nombre_real = "No especificado"
        try:
            conn = sqlite3.connect("datos/base_datos.db") # Ajusta tu ruta si es distinta
            cursor = conn.cursor()
            cursor.execute("SELECT nombre FROM productos WHERE asin = ?", (asin_ejemplo,))
            resultado_bd = cursor.fetchone()
            if resultado_bd:
                nombre_real = resultado_bd[0]
            conn.close()
            print(f"[TEST DB] Nombre extraído de SQLite: {nombre_real[:30]}...")
        except Exception as e:
            print(f"[TEST DB ERROR] No se pudo leer SQLite: {e}")

        print(f"Pregunta: {pregunta_usuario}")
        t_inicio = time.time()
        
        # 2. SE LO PASAMOS AL MOTOR (Ahora sí, 100% automático)
        resultado = await motor.consultar(
            pregunta=pregunta_usuario, 
            asin_producto=asin_ejemplo,
            nombre_producto=nombre_real
        )
        
        # ... (resto del código de impresión del streaming)
        print("\nRespuesta de la IA:")
        async for chunk in resultado:
            texto = chunk.delta if hasattr(chunk, 'delta') else chunk
            print(texto, end="", flush=True)
        print("\n--------------------------------------\n")

    asyncio.run(prueba_local())