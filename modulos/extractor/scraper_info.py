import os
import requests
from bs4 import BeautifulSoup

class ExtractorDatosOficiales:
    def __init__(self, marketplace="com.mx"):
        self.marketplace = marketplace
        # Agregamos unas cabeceras un poco más completas para intentar camuflarnos mejor
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "es-MX,es;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Referer": f"https://www.amazon.{self.marketplace}/"
        }

    def obtener_ficha_tecnica(self, asin: str) -> dict:
        """Extrae el nombre y características oficiales del producto y guarda el HTML para depuración."""
        url = f"https://www.amazon.{self.marketplace}/dp/{asin}"
        datos = {"asin": asin, "nombre": f"Producto ASIN: {asin}", "caracteristicas": []}

        try:
            print(f"\n[SCRAPER DEBUG] 1. Haciendo petición GET a: {url}")
            response = requests.get(url, headers=self.headers, timeout=10)
            print(f"[SCRAPER DEBUG] 2. Código de estado HTTP recibido: {response.status_code}")
            
            # --- BLOQUE DE AUDITORÍA: GUARDAR HTML CRUDO ---
            os.makedirs(os.path.join("datos", "procesados"), exist_ok=True)
            ruta_debug = os.path.join("datos", "procesados", f"debug_amazon_{asin}.html")
            
            with open(ruta_debug, "w", encoding="utf-8") as f:
                f.write(response.text)
            print(f"[SCRAPER DEBUG] 3. HTML crudo guardado exitosamente en: '{ruta_debug}'")
            # -----------------------------------------------

            if response.status_code == 200:
                soup = BeautifulSoup(response.text, "html.parser")
                
                titulo_tag = soup.find("span", id="productTitle")
                if titulo_tag:
                    datos["nombre"] = titulo_tag.text.strip()
                    print(f"[SCRAPER DEBUG] 4. Éxito: Título capturado -> {datos['nombre'][:30]}...")
                else:
                    print("[SCRAPER DEBUG] 4. Falla: No se encontró la etiqueta <span id='productTitle'> en el HTML.")
                
                bullets_ul = soup.find("div", id="feature-bullets")
                if bullets_ul:
                    for item in bullets_ul.find_all("span", class_="a-list-item"):
                        texto = item.text.strip()
                        if texto and not texto.startswith("Ocultar"): 
                            datos["caracteristicas"].append(texto)
                    print(f"[SCRAPER DEBUG] 5. Éxito: {len(datos['caracteristicas'])} viñetas técnicas capturadas.")
                else:
                    print("[SCRAPER DEBUG] 5. Falla: No se encontró la etiqueta <div id='feature-bullets'> en el HTML.")
            else:
                print(f"[SCRAPER DEBUG] ERROR: Amazon no devolvió un código 200. Rechazó la petición.")

        except Exception as e:
            print(f"[ADVERTENCIA CRÍTICA] Error ejecutando requests sobre {asin}: {e}")

        return datos

# Bloque para probar de forma aislada
if __name__ == "__main__":
    extractor = ExtractorDatosOficiales()
    resultado = extractor.obtener_ficha_tecnica("B08634653D")
    
    print("\n[RESULTADO FINAL DEL DICCIONARIO]")
    print(f"Nombre: {resultado['nombre']}")
    print(f"Total características: {len(resultado['caracteristicas'])}")
    
    print("\n--- DETALLE DE CARACTERÍSTICAS ---")
    for i, viñeta in enumerate(resultado['caracteristicas'], 1):
        print(f"{i}. {viñeta}")