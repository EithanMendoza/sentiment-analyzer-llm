# AgenteLocalParaResenas 🤖🛒

Un motor analítico RAG (Generación Aumentada por Recuperación) de ejecución local diseñado para extraer, vectorizar y analizar reseñas de productos de Amazon. Construido con FastAPI, LlamaIndex, ChromaDB y Ollama.

## Arquitectura del Proyecto

* **Backend:** Python con FastAPI.
* **Extracción de Datos:** BeautifulSoup (Ficha Técnica) y Apify (Reseñas profundas).
* **Base de Datos Relacional:** SQLite (Gestión de usuarios, historial de chats y metadatos de productos).
* **Base de Datos Vectorial:** ChromaDB (Almacenamiento de embeddings para búsquedas semánticas por ASIN).
* **Inferencia Local:** Ollama (Modelos LLM y Embeddings ejecutados en hardware local).

## Prerrequisitos

Para ejecutar este proyecto, necesitas tener instalado:
1. Python 3.10 o superior.
2. [Ollama](https://ollama.com/) instalado y ejecutándose en tu máquina local.
3. Los modelos de Ollama descargados previamente. Ejecuta en tu terminal:
   - `ollama run qwen2.5` (o el modelo LLM de tu preferencia).
   - `ollama pull nomic-embed-text` (para la vectorización).

## Instalación y Configuración

1. Clona este repositorio.
2. Crea un entorno virtual y actívalo:
   `python -m venv venv`
3. Instala las dependencias:
   `pip install -r requirements.txt`
4. Crea un archivo `.env` en la raíz con tus variables de entorno:
   - `APIFY_TOKEN=tu_token_aqui`

## Ejecución

Inicia el servidor local de FastAPI con Uvicorn:
`uvicorn main:app --reload`

El servidor verificará automáticamente la integridad de las bases de datos SQLite e inicializará el motor RAG en memoria. Accede a la documentación interactiva en `http://localhost:8000/docs`.