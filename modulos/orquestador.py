import os
import asyncio
from dotenv import load_dotenv

# --- IMPORTACIONES ACTUALIZADAS (APIFY) ---
from modulos.extractor.scraper_info import ExtractorDatosOficiales
from modulos.extractor.apify_client import extraer_resenas_apify
from modulos.base_datos.operaciones.productos import guardar_o_actualizar_producto
from modulos.base_datos.operaciones.resenas import guardar_resenas_masivas
# ------------------------------------------

from modulos.indexador.indexador import IndexadorRAG

load_dotenv()

estados_tareas = {}

class ControladorRAG:
    """
    Orquesta el flujo completo: 
    1. Scraping ligero (Características) -> Guardado SQL
    2. Scraping profundo (Apify Cloud) -> Guardado SQL
    3. Vectorización -> Guardado ChromaDB
    """
    def __init__(self):
        self.extractor_oficial = ExtractorDatosOficiales()
        self.indexador = IndexadorRAG()

    def _adaptar_formato_para_sqlite(self, datos_apify, asin):
        """🆕 TRADUCTOR CRÍTICO: Mapea las llaves en español al formato de columnas en inglés que exige SQLite."""
        datos_sqlite = []
        for item in datos_apify:
            adaptado = {
                "review_id": str(item.get("id", "sin_id")),
                "asin": str(asin).strip().upper(),
                "author": item.get("autor", "Anónimo"),
                "title": item.get("titulo_comentario", "Sin título"),
                "body": item.get("texto", ""),
                "rating": int(item.get("estrellas", 0))
            }
            # Solo agregamos registros con contenido de texto válido
            if len(adaptado["body"].strip()) >= 5:
                datos_sqlite.append(adaptado)
        return datos_sqlite

    def _adaptar_formato_para_llamaindex(self, datos_apify, asin):
        """Traduce el JSON que devuelve Apify y le inyecta el ASIN en los metadatos."""
        datos_adaptados = []
        for item in datos_apify:
            adaptado = {
                "id": item.get("id", "sin_id"),
                "autor": item.get("autor", "Anónimo"),
                "estrellas": item.get("estrellas", 0),
                "titulo_comentario": item.get("titulo_comentario", "Sin título"),
                "texto": item.get("texto", ""),
                "fuente": item.get("fuente", "Amazon vía Apify"),
                "metadatos": {
                    "asin": asin, # <--- CRUCIAL: Añadimos el ASIN a los metadatos de ChromaDB
                    "fecha_publicacion": item.get("fecha_publicacion", "Desconocida"),
                    "compra_verificada": item.get("compra_verificada", False),
                    "variante": item.get("variante", "")
                }
            }
            datos_adaptados.append(adaptado)
        return datos_adaptados

    def procesar_nuevo_producto(self, asin: str, marketplace: str = "com.mx", usuario_id: str = "desconocido"):
        """
        Orquesta el flujo completo de scraping, almacenamiento relacional e indexación
        vectorial amarrando estrictamente la información al usuario en sesión.
        """
        print(f"\n[ORQUESTADOR] 1. Iniciando análisis completo para ASIN: {asin} (Usuario: {usuario_id})")
        estados_tareas[asin] = "procesando"
        
        try:
            # ==========================================
            # FASE 1: METADATOS OFICIALES (BeautifulSoup -> SQLite)
            # ==========================================
            print("[ORQUESTADOR] Fase 1: Extrayendo ficha técnica...")
            datos_oficiales = self.extractor_oficial.obtener_ficha_tecnica(asin)
            
            # 🚀 CORRECCIÓN CLAVE: Pasamos el usuario_id para que no quede como 'desconocido'
            guardar_o_actualizar_producto(
                asin=asin, 
                nombre=datos_oficiales["nombre"], 
                caracteristicas=datos_oficiales["caracteristicas"],
                usuario_id=str(usuario_id)  # <-- Asegura el dueño en la base de datos
            )
            
            # ==========================================
            # FASE 2: RESEÑAS DE USUARIOS (Apify Cloud -> SQLite)
            # ==========================================
            print("[ORQUESTADOR] Fase 2: Extrayendo reseñas de clientes usando Apify...")
            
            # Llamamos a tu cliente de Apify pasándole el ASIN
            datos_limpios = extraer_resenas_apify(asin=asin)
            
            if not datos_limpios:
                print(f"[ORQUESTADOR ERROR] No se obtuvieron reseñas de Apify para {asin}.")
                estados_tareas[asin] = "error"
                return False

            # Guardamos la copia de seguridad relacional
            guardar_resenas_masivas(asin=asin, resenas=datos_limpios)

            # ==========================================
            # FASE 3: INDEXACIÓN VECTORIAL (Transformación -> ChromaDB)
            # ==========================================
            print(f"[ORQUESTADOR] Fase 3: Vectorizando {len(datos_limpios)} reseñas...")
            
            # Le pasamos el ASIN a la adaptación para que quede sellado en los vectores.
            # NOTA: Si deseas aislar los vectores por usuario en LlamaIndex/ChromaDB,
            # puedes pasar también el usuario_id dentro de esta función adaptadora.
            datos_estructurados = self._adaptar_formato_para_llamaindex(datos_limpios, asin)
            
            self.indexador.construir_indice(datos_estructurados)
            
            print(f"[ORQUESTADOR ÉXITO] Pipeline finalizado correctamente para {asin} (Usuario: {usuario_id}).")
            estados_tareas[asin] = "completado"
            return True
            
        except Exception as e:
            print(f"[ORQUESTADOR ERROR CRÍTICO] Falló el proceso para {asin}: {e}")
            estados_tareas[asin] = "error"
            return False