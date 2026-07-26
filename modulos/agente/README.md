# Módulo de Agente RAG (Motor Analítico Lineal)

Este módulo implementa un motor RAG optimizado para inferencia en CPU utilizando LlamaIndex, ChromaDB y Ollama.

## Estructura de Archivos (Principios SOLID)

- **`config.py`**: Centraliza todas las configuraciones globales. 
  - *Para tus compañeros:* Modifica aquí los hilos (`num_thread`) y el modelo si tu laptop tiene menos o más recursos.
- **`modelos.py`**: Se encarga exclusivamente de instanciar y registrar los modelos de Ollama (`qwen2.5:1.5b` y `nomic-embed-text`) en el entorno global.
- **`almacen.py`**: Administra la persistencia y conexión exclusiva con la base de datos vectorial en ChromaDB.
- **`motor.py`**: Orquesta los componentes anteriores, define la plantilla estricta de prompts anti-alucinación y expone el método de consulta para FastAPI.

## ¿Cómo cambiar los parámetros según tu laptop?
Abre `config.py` y ajusta los valores de `CONFIG_LLM`:
- Si tienes un procesador con más núcleos, puedes subir `num_thread` (ej. 4 u 8).
- Si tienes poca RAM, mantén o reduce el `num_ctx`.

# ADR 001: Implementación de RAG Híbrido y Bypass para Streaming Asíncrono Nativo

## Fecha
Julio 2026

## Estado
Aceptado

## Contexto y Problema
Durante el desarrollo del motor analítico de reseñas basado en LlamaIndex y FastAPI (ejecutado en CPU con modelos locales), nos enfrentamos a dos problemas críticos en la arquitectura de recuperación y generación:

1. **Silos de Información (Alucinaciones / Cláusula de escape):** Los metadatos exactos del producto (Título, ASIN, Especificaciones JSON) residían únicamente en la base de datos relacional (SQLite), mientras que la IA solo consultaba la base vectorial (ChromaDB) que contenía las opiniones. Al no encontrar datos técnicos en las reseñas de los usuarios, la IA era incapaz de identificar el producto exacto y activaba falsamente las reglas estrictas anti-alucinación, respondiendo que carecía de información.
2. **Falso Streaming ("El bloque gigante"):** Al utilizar la abstracción estándar `as_query_engine(streaming=True)` de LlamaIndex con el LLM local, el sistema sufría un bloqueo. El tiempo hasta el primer token (TTFT) era de ~70 segundos (debido al procesamiento de ingestión en CPU), tras lo cual la capa intermedia de LlamaIndex empaquetaba toda la respuesta y la enviaba en un único chunk masivo (con un tiempo real de escritura de ~0.04s). Esto destruía la experiencia de usuario (UX) en el frontend (React), eliminando el efecto visual de escritura en tiempo real.

## Decisión
Para resolver estos obstáculos, decidimos abandonar las abstracciones de alto nivel de LlamaIndex y construir un **RAG Manual Híbrido** mediante las siguientes modificaciones:

1. **Inyección de Contexto Híbrido:** Antes de invocar al motor de IA, el endpoint de FastAPI recupera los metadatos de SQLite (`obtener_producto`) y formatea las características técnicas. Estos datos "oficiales" se inyectan dinámicamente en el prompt junto con los resultados vectoriales recuperados de ChromaDB.
2. **Bypass del QueryEngine:** Se eliminó el uso de `QueryEngine`. En su lugar, el orquestador en `motor.py` gestiona la recuperación y generación en pasos asíncronos explícitos:
   * Extracción de contexto usando `retriever.aretrieve()`.
   * Construcción manual del Súper-Prompt.
   * Invocación del streaming asíncrono nativo del LLM usando `Settings.llm.astream_complete(prompt_final)`.

## Consecuencias

* **Positivas:**
  * **Identidad de producto recuperada:** La IA logra cruzar exitosamente las especificaciones técnicas (SQLite) con las reseñas (ChromaDB), mejorando la precisión de las respuestas.
  * **Streaming real restaurado:** Al conectar el endpoint directamente al generador `astream_complete()` de Ollama, logramos un flujo real token por token (con un tiempo de escritura comprobado de ~40 segundos a ~12 TPS), habilitando la lectura fluida en el cliente de React.
  * **Código asíncrono optimizado:** Se eliminaron los cuellos de botella síncronos en el backend, liberando el hilo principal de FastAPI.

* **Negativas / Compromisos:**
  * **Mantenimiento del prompt:** Al descartar las herramientas automáticas de LlamaIndex, asumimos la responsabilidad técnica de construir, concatenar y dar mantenimiento manual al Prompt dentro de la lógica del motor.
  * **Limitación de hardware aceptada:** El TTFT (Time To First Token) se mantiene alto (~50s) debido al cálculo del contexto inicial en CPU, pero la mejora en la fluidez de entrega justifica la espera inicial.