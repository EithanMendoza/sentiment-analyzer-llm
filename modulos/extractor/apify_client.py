import os
import re
import requests
from dotenv import load_dotenv

load_dotenv()

# === 1. CAPA DE SANITIZACIÓN ===
def limpiar_texto_resena(texto_crudo: str) -> str:
    """Elimina la basura de la interfaz de Amazon del texto extraído."""
    if not texto_crudo:
        return ""
        
    texto = texto_crudo
    
    frases_basura = [
        "Brief content visible, double tap to read full content.",
        "Full content visible, double tap to read brief content.",
        "Leer más Leer menos",
        "Leer más",
        "Read more"
    ]
    
    for frase in frases_basura:
        texto = texto.replace(frase, "")
        
    # Convierte múltiples espacios o saltos de línea en uno solo
    texto = re.sub(r'\s+', ' ', texto)
    return texto.strip()

# === 2. CAPA DE EXTRACCIÓN ===
class ExtractorAmazonReef:
    def __init__(self, api_token: str = None):
        # Si no se pasa el token, lo leemos directo del archivo .env
        self.api_token = api_token or os.getenv("APIFY_TOKEN")
        self.actor_id = "reefapi~amazon-reviews-scraper"

    def extraer_y_limpiar(self, asin: str, marketplace: str = "com.mx"):
        print(f"\n[EXTRACTOR] Conectando con Reef API para ASIN: {asin} ({marketplace})...")
        
        if not self.api_token:
            print("[ERROR EXTRACTOR] No se encontró el token de Apify.")
            return None

        url = f"https://api.apify.com/v2/acts/{self.actor_id}/run-sync-get-dataset-items?token={self.api_token}"
        
        payload = {
            "asin": asin,
            "marketplace": marketplace,
            "sort": "recent"
        }

        try:
            response = requests.post(url, json=payload, timeout=120)
            response.raise_for_status()
            
            datos_crudos = response.json()
            print(f"[EXTRACTOR] ✅ Datos recibidos. Limpiando {len(datos_crudos)} registros...")
            
            # === 3. PROCESAMIENTO Y MAPEO DE LLAVES ===
            datos_limpios = []
            for item in datos_crudos:
                cuerpo_crudo = item.get("body") or item.get("text", "")
                cuerpo_limpio = limpiar_texto_resena(cuerpo_crudo)
                
                if cuerpo_limpio:
                    # Mapeamos las llaves crudas de Apify al formato que espera tu orquestador
                    resena_mapeada = {
                        "id": item.get("id") or item.get("reviewId", "sin_id"),
                        "autor": item.get("author") or item.get("name", "Anónimo"),
                        "estrellas": int(item.get("rating") or item.get("stars", 0)),
                        "titulo_comentario": item.get("reviewTitle") or item.get("title", "Sin título"),
                        "texto": cuerpo_limpio,
                        "fuente": "Amazon vía Apify",
                        "fecha_publicacion": item.get("date") or item.get("reviewDate", "Desconocida"),
                        "compra_verificada": bool(item.get("isVerified") or item.get("verifiedPurchase", False)),
                        "variante": item.get("variant") or item.get("options", "")
                    }
                    datos_limpios.append(resena_mapeada)
                    
            print(f"[EXTRACTOR] ✨ Limpieza completada. {len(datos_limpios)} reseñas listas.")
            return datos_limpios
            
        except requests.exceptions.RequestException as e:
            print(f"[ERROR EXTRACTOR] Error de red o token inválido: {e}")
            return None


# Función de compatibilidad por si tu orquestador la llama directamente de forma procedural
def extraer_resenas_apify(asin: str, marketplace: str = "com.mx"):
    extractor = ExtractorAmazonReef()
    return extractor.extraer_y_limpiar(asin, marketplace)