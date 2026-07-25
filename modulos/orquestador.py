import os
import asyncio
from dotenv import load_dotenv

# --- NUEVAS IMPORTACIONES ---
from modulos.extractor.apify_client import ExtractorAmazonReef
from modulos.extractor.scraper_info import ExtractorDatosOficiales
from modulos.base_datos.operaciones.productos import guardar_o_actualizar_producto
from modulos.base_datos.operaciones.resenas import guardar_resenas_masivas
# ---------------------------

from modulos.indexador.indexador import IndexadorRAG

load_dotenv()

estados_tareas = {}

class ControladorRAG:
    """
    Orquesta el flujo completo: 
    1. Scraping ligero (Características) -> Guardado SQL
    2. Scraping profundo (Apify Reseñas) -> Guardado SQL
    3. Vectorización -> Guardado ChromaDB
    """
    def __init__(self):
        self.api_token = os.getenv("APIFY_TOKEN")
        if not self.api_token:
            raise ValueError("Falta el APIFY_TOKEN en las variables de entorno.")
            
        self.extractor_apify = ExtractorAmazonReef(api_token=self.api_token)
        self.extractor_oficial = ExtractorDatosOficiales() # <--- Instanciamos BS4
        self.indexador = IndexadorRAG()

    def _adaptar_formato_para_llamaindex(self, datos_apify, asin):
        """Traduce el JSON de Apify y le inyecta el ASIN en los metadatos."""
        datos_adaptados = []
        for item in datos_apify:
            adaptado = {
                "id": item.get("review_id", "sin_id"),
                "autor": item.get("author", "Anónimo"),
                "estrellas": item.get("rating", 0),
                "titulo_comentario": item.get("title", "Sin título"),
                "texto": item.get("body", ""),
                "fuente": "Amazon vía Reef API",
                "metadatos": {
                    "asin": asin, # <--- CRUCIAL: Añadimos el ASIN a los metadatos de ChromaDB
                    "fecha_publicacion": item.get("date", "Desconocida"),
                    "compra_verificada": item.get("verified", False)
                }
            }
            datos_adaptados.append(adaptado)
        return datos_adaptados

    def procesar_nuevo_producto(self, asin: str, marketplace: str = "com.mx"):
        print(f"\n[ORQUESTADOR] 1. Iniciando análisis completo para ASIN: {asin}")
        estados_tareas[asin] = "procesando" 
        
        try:
            # ==========================================
            # FASE 1: METADATOS OFICIALES (BeautifulSoup -> SQLite)
            # ==========================================
            print("[ORQUESTADOR] Fase 1: Extrayendo ficha técnica...")
            datos_oficiales = self.extractor_oficial.obtener_ficha_tecnica(asin)
            
            # Guardamos en la base de datos relacional
            guardar_o_actualizar_producto(
                asin=asin, 
                nombre=datos_oficiales["nombre"], 
                caracteristicas=datos_oficiales["caracteristicas"]
            )
            
            # ==========================================
            # FASE 2: RESEÑAS DE USUARIOS (Apify -> SQLite)
            # ==========================================
            print("[ORQUESTADOR] Fase 2: Extrayendo reseñas de clientes...")
            datos_limpios = self.extractor_apify.extraer_y_limpiar(asin=asin, marketplace=marketplace)
            
            if not datos_limpios:
                print(f"[ORQUESTADOR ERROR] No se obtuvieron reseñas para {asin}.")
                estados_tareas[asin] = "error"
                return False

            # Guardamos la copia de seguridad relacional
            guardar_resenas_masivas(asin=asin, resenas=datos_limpios)

            # ==========================================
            # FASE 3: INDEXACIÓN VECTORIAL (Transformación -> ChromaDB)
            # ==========================================
            print(f"[ORQUESTADOR] Fase 3: Vectorizando {len(datos_limpios)} reseñas...")
            
            # Le pasamos el ASIN a la adaptación para que quede sellado en los vectores
            datos_estructurados = self._adaptar_formato_para_llamaindex(datos_limpios, asin)
            
            self.indexador.construir_indice(datos_estructurados)
            
            print(f"[ORQUESTADOR ÉXITO] Pipeline finalizado correctamente para {asin}.")
            estados_tareas[asin] = "completado" 
            return True
            
        except Exception as e:
            print(f"[ORQUESTADOR ERROR CRÍTICO] Falló el proceso para {asin}: {e}")
            estados_tareas[asin] = "error"
            return False