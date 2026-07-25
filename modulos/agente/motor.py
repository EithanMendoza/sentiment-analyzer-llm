"""
Módulo: motor.py
Responsabilidad: Orquestar los componentes del sistema (configuración, modelos y 
almacenamiento vectorial). Define la plantilla estricta de prompts anti-alucinación 
para modelos pequeños y expone el método de consulta optimizado para la API de FastAPI.
"""

from llama_index.core import PromptTemplate
from .config import SIMILARITY_TOP_K
from .modelos import configurar_modelos
from .almacen import obtener_indice_vectorial

class MockStreamingResponse:
    """Simula el formato de respuesta de LlamaIndex para no romper el endpoint de chat."""
    @property
    def response_gen(self):
        yield "El motor aún no tiene datos. Por favor, procesa un enlace de Amazon primero."

class MotorAnaliticoLineal:
    """
    Motor RAG optimizado para inferencia en CPU.
    Implementa Lazy Loading para soportar arranques en frío (servidor vacío).
    """
    def __init__(self):
        configurar_modelos()
        self.index = None
        self.query_engine = None
        # Intentamos cargar el motor, pero si falla, no detenemos el servidor
        self._intentar_cargar_motor()

    def _intentar_cargar_motor(self):
        """Intenta conectarse a ChromaDB de forma segura."""
        try:
            self.index = obtener_indice_vectorial()
            if self.index:
                self.query_engine = self._construir_motor()
        except Exception as e:
            print("[INFO] Arranque en frío: No hay base vectorial aún. El motor esperará datos.")

    def _construir_motor(self):
        """Ensambla el motor de consulta lineal con reglas anti-alucinación."""
        plantilla_estricta = (
            "Eres un analista de reseñas de productos. Sé directo y conciso.\n"
            "Responde a la consulta basándote ÚNICAMENTE en este contexto:\n"
            "---------------------\n"
            "{context_str}\n"
            "---------------------\n"
            "REGLAS CRÍTICAS:\n"
            "1. CERO CRUCE DE DATOS: Cada bloque '=== RESEÑA DE CLIENTE ===' es totalmente independiente.\n"
            "2. ATRIBUCIÓN ESTRICTA: El 'TEXTO DE LA OPINIÓN' y la 'CALIFICACIÓN' pertenecen EXCLUSIVAMENTE al 'AUTOR' escrito en ese mismo bloque.\n"
            "3. NOMBRES VÁLIDOS: Nombres genéricos como 'Cliente Amazon', 'Anónimo' o apodos son nombres válidos. Úsalos tal cual aparecen.\n"
            "4. NO ASUMAS NADA: Si el texto no menciona el tipo de producto, no lo inventes.\n"
            "5. CLÁUSULA DE ESCAPE: Si la información solicitada no está en el contexto, responde EXACTAMENTE: 'No cuento con registros suficientes en las opiniones.'\n\n"
            "Consulta: {query_str}\n"
            "Respuesta:"
        )
        qa_template = PromptTemplate(plantilla_estricta)

        print("[INFO] Motor lineal ensamblado y listo.")
        return self.index.as_query_engine(
            similarity_top_k=SIMILARITY_TOP_K,
            text_qa_template=qa_template,
            streaming=True
        )

    def consultar(self, pregunta: str, asin_producto: str = None):
        """Punto de entrada para FastAPI con Lazy Loading."""
        
        # 1. Si no hay motor, intentamos cargarlo de nuevo (quizás ya hubo scraping)
        if not self.query_engine:
            self._intentar_cargar_motor()
            
        # 2. Si sigue sin haber motor (sigue vacío), devolvemos la respuesta mockeada
        if not self.query_engine:
            return MockStreamingResponse()

        # 3. Si todo está en orden, inyectamos el ASIN y consultamos
        if asin_producto:
            pregunta_enriquecida = f"[Nota para la IA: El producto analizado es el ASIN {asin_producto}] {pregunta}"
        else:
            pregunta_enriquecida = pregunta
            
        return self.query_engine.query(pregunta_enriquecida)

# Bloque de prueba local
if __name__ == "__main__":
    motor = MotorAnaliticoLineal()
    print("\n--- PRUEBA DE VELOCIDAD Y CONTEXTO ---")
    asin_ejemplo = "B0CYWFH5Y9"
    pregunta_usuario = "¿Qué dicen las reseñas sobre la duración de la batería?"
    
    resultado = motor.consultar(pregunta=pregunta_usuario, asin_producto=asin_ejemplo)
    
    # Soporte para la prueba local dependiendo de si es mock o real
    if hasattr(resultado, "response_gen"):
        print("\nRespuesta de la IA:")
        for fragmento in resultado.response_gen:
            print(fragmento, end="", flush=True)
        print()
    else:
        print(f"\nRespuesta de la IA:\n{resultado}")