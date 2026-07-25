import os
import re
import requests

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
    def __init__(self, api_token: str):
        self.api_token = api_token
        self.actor_id = "reefapi~amazon-reviews-scraper"

    def extraer_y_limpiar(self, asin: str, marketplace: str = "com.mx"):
        print(f"\n[EXTRACTOR] Conectando con Reef API para ASIN: {asin} ({marketplace})...")
        
        url = f"https://api.apify.com/v2/acts/{self.actor_id}/run-sync-get-dataset-items?token={self.api_token}"
        
        payload = {
            "asin": asin,
            "marketplace": marketplace,
            "sort": "recent"
        }

        try:
            # Aumentamos el timeout a 120s porque a veces las APIs de scraping tardan en levantar
            response = requests.post(url, json=payload, timeout=120)
            response.raise_for_status()
            
            datos_crudos = response.json()
            print(f"[EXTRACTOR] ✅ Datos recibidos. Limpiando {len(datos_crudos)} registros...")
            
            # === 3. PROCESAMIENTO EN TIEMPO REAL ===
            datos_limpios = []
            for item in datos_crudos:
                cuerpo_crudo = item.get("body", "")
                cuerpo_limpio = limpiar_texto_resena(cuerpo_crudo)
                
                # Solo conservamos la reseña si quedó texto útil después de limpiar
                if cuerpo_limpio:
                    item["body"] = cuerpo_limpio # Reemplazamos el texto sucio
                    datos_limpios.append(item)
                    
            print(f"[EXTRACTOR] ✨ Limpieza completada. {len(datos_limpios)} reseñas listas.")
            return datos_limpios
            
        except requests.exceptions.RequestException as e:
            print(f"[ERROR EXTRACTOR] Error de red o token inválido: {e}")
            return None