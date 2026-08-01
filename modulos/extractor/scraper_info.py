import os
import time
import random
import requests
from bs4 import BeautifulSoup

class ExtractorDatosOficiales:
    def __init__(self, marketplace="com.mx"):
        self.marketplace = marketplace
        # 1. Usar una sesión permite mantener cookies entre peticiones, como un navegador real
        self.session = requests.Session() 
        
        # 2. Lista de User-Agents modernos para rotar en caso de bloqueos
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/122.0.0.0 Safari/537.36"
        ]

    def _obtener_headers(self):
        """Genera cabeceras dinámicas y modernas para evadir detección básica."""
        return {
            "User-Agent": random.choice(self.user_agents),
            "Accept-Language": "es-MX,es;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            # Cabeceras Client-Hints (muy importantes hoy en día)
            "Sec-Ch-Ua": '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Upgrade-Insecure-Requests": "1",
            # Fingir que venimos de una búsqueda de Google suele dar más confianza
            "Referer": "https://www.google.com/" 
        }

    def obtener_ficha_tecnica(self, asin: str, reintentos: int = 3) -> dict:
        """Extrae el nombre y características oficiales del producto con detección de CAPTCHA."""
        url = f"https://www.amazon.{self.marketplace}/dp/{asin}"
        datos = {"asin": asin, "nombre": f"Producto ASIN: {asin}", "caracteristicas": []}

        for intento in range(1, reintentos + 1):
            try:
                print(f"\n[SCRAPER DEBUG] Intento {intento}/{reintentos} - Haciendo petición GET a: {url}")
                
                # 3. Pausa aleatoria para no saturar y simular comportamiento humano
                time.sleep(random.uniform(1.5, 3.5))
                
                response = self.session.get(url, headers=self._obtener_headers(), timeout=15)
                print(f"[SCRAPER DEBUG] Código HTTP: {response.status_code}")
                
                # --- BLOQUE DE AUDITORÍA ---
                os.makedirs(os.path.join("datos", "procesados"), exist_ok=True)
                ruta_debug = os.path.join("datos", "procesados", f"debug_amazon_{asin}.html")
                with open(ruta_debug, "w", encoding="utf-8") as f:
                    f.write(response.text)
                # -----------------------------------------------

                if response.status_code == 200:
                    # 4. 🚨 DETECCIÓN EXPLÍCITA DE CAPTCHA 🚨
                    if "/errors_page/validateCaptcha" in response.text or "api-services-support@amazon.com" in response.text:
                        print("[SCRAPER DEBUG] 🛑 ¡ALERTA! Amazon bloqueó la petición con un CAPTCHA.")
                        if intento < reintentos:
                            print("[SCRAPER DEBUG] 🔄 Reintentando con nueva huella dactilar...")
                            continue
                        else:
                            print("[SCRAPER DEBUG] ❌ Se agotaron los reintentos. Extracción abortada.")
                            break

                    soup = BeautifulSoup(response.text, "html.parser")
                    
                    titulo_tag = soup.find("span", id="productTitle")
                    if titulo_tag:
                        datos["nombre"] = titulo_tag.text.strip()
                        print(f"[SCRAPER DEBUG] Éxito: Título capturado -> {datos['nombre'][:30]}...")
                    else:
                        print("[SCRAPER DEBUG] Falla: No se encontró la etiqueta <span id='productTitle'>.")
                    
                    bullets_ul = soup.find("div", id="feature-bullets")
                    if bullets_ul:
                        for item in bullets_ul.find_all("span", class_="a-list-item"):
                            texto = item.text.strip()
                            if texto and not texto.startswith("Ocultar"): 
                                datos["caracteristicas"].append(texto)
                        print(f"[SCRAPER DEBUG] Éxito: {len(datos['caracteristicas'])} viñetas capturadas.")
                    else:
                        print("[SCRAPER DEBUG] Falla: No se encontró la etiqueta <div id='feature-bullets'>.")
                    
                    # Si llegamos aquí sin CAPTCHA, el scraping fue un éxito; salimos del bucle.
                    break 
                
                elif response.status_code == 503:
                    print("[SCRAPER DEBUG] 🛑 Error 503: Servicio no disponible (posible bloqueo de IP).")
                else:
                    print(f"[SCRAPER DEBUG] ERROR: Código {response.status_code} inesperado.")

            except Exception as e:
                print(f"[ADVERTENCIA CRÍTICA] Error ejecutando requests sobre {asin}: {e}")

        return datos

# Bloque para probar de forma aislada
if __name__ == "__main__":
    extractor = ExtractorDatosOficiales()
    # Probando con el ASIN que falló anteriormente
    resultado = extractor.obtener_ficha_tecnica("B0D44135S2")
    
    print("\n[RESULTADO FINAL DEL DICCIONARIO]")
    print(f"Nombre: {resultado['nombre']}")
    print(f"Total características: {len(resultado['caracteristicas'])}")
    
    if resultado['caracteristicas']:
        print("\n--- DETALLE DE CARACTERÍSTICAS ---")
        for i, viñeta in enumerate(resultado['caracteristicas'], 1):
            print(f"{i}. {viñeta}")