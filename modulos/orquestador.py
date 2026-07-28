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
            id_seguro = item.get("review_id", item.get("id", "sin_id"))
            adaptado = {
                "id": id_seguro,
                "asin": asin, # <--- MUÉVELO AQUÍ (Nivel principal)
                "autor": item.get("autor", "Anónimo"),
                "estrellas": item.get("estrellas", 0),
                "titulo_comentario": item.get("titulo_comentario", "Sin título"),
                "texto": item.get("texto", ""),
                "fuente": item.get("fuente", "Amazon vía Apify"),
                "metadatos": {
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
        vectorial garantizando la correcta vinculación con ChromaDB y SQLite.
        """
        asin_limpio = str(asin).strip().upper()
        uid_limpio = str(usuario_id).strip()
        print(f"\n[ORQUESTADOR] 1. Iniciando análisis completo para ASIN: {asin_limpio} (Usuario: {uid_limpio})")
        estados_tareas[asin_limpio] = "procesando"
        
        try:
            # ==========================================
            # FASE 1: METADATOS OFICIALES (BeautifulSoup -> SQLite)
            # ==========================================
            print("[ORQUESTADOR] Fase 1: Extrayendo ficha técnica...")
            datos_oficiales = self.extractor_oficial.obtener_ficha_tecnica(asin_limpio)
            
            guardar_o_actualizar_producto(
                asin=asin_limpio, 
                nombre=datos_oficiales.get("nombre", f"Producto ASIN: {asin_limpio}"), 
                caracteristicas=datos_oficiales.get("caracteristicas", []),
                usuario_id=uid_limpio
            )
            
            # ==========================================
            # FASE 2: RESEÑAS DE USUARIOS (Apify Cloud -> SQLite)
            # ==========================================
            print("[ORQUESTADOR] Fase 2: Extrayendo reseñas de clientes usando Apify...")
            datos_limpios = extraer_resenas_apify(asin=asin_limpio, marketplace=marketplace)
            
            if not datos_limpios:
                print(f"[ORQUESTADOR ERROR] No se obtuvieron reseñas de Apify para {asin_limpio}.")
                estados_tareas[asin_limpio] = "error_sin_resenas"
                return False

            # Guardamos la copia de seguridad relacional en SQLite
            guardar_resenas_masivas(asin=asin_limpio, resenas=datos_limpios)

            # ==========================================
            # FASE 3: INDEXACIÓN VECTORIAL (Transformación -> ChromaDB)
            # ==========================================
            print(f"[ORQUESTADOR] Fase 3: Vectorizando {len(datos_limpios)} reseñas en ChromaDB...")
            datos_estructurados = self._adaptar_formato_para_llamaindex(datos_limpios, asin_limpio)
            
            # 🚀 CORRECCIÓN CRÍTICA: Se envía usuario_id explícitamente a ChromaDB
            self.indexador.construir_indice(datos_estructurados, usuario_id=uid_limpio)
            
            print(f"[ORQUESTADOR ÉXITO] Pipeline finalizado correctamente para {asin_limpio}.")
            estados_tareas[asin_limpio] = "completado"
            return True
            
        except Exception as e:
            print(f"[ORQUESTADOR ERROR CRÍTICO] Falló el proceso para {asin_limpio}: {e}")
            estados_tareas[asin_limpio] = "error"
            return False