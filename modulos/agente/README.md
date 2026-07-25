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