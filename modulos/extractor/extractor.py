import json
import os
from datetime import datetime
from playwright.sync_api import sync_playwright
import urllib.parse

class ExtractorEspecifico:
    # Modificamos la ruta para que apunte a la carpeta datos/
    def __init__(self, archivo_salida="datos/reseñas_crudas.json"):
        self.archivo_salida = archivo_salida

    def _guardar_json(self, nuevos_datos: list[dict]):
        datos_existentes = []
        if os.path.exists(self.archivo_salida):
            with open(self.archivo_salida, "r", encoding="utf-8") as f:
                try:
                    datos_existentes = json.load(f)
                except json.JSONDecodeError:
                    datos_existentes = []

        datos_existentes.extend(nuevos_datos)
        with open(self.archivo_salida, "w", encoding="utf-8") as f:
            json.dump(datos_existentes, f, ensure_ascii=False, indent=4)
            
        print(f"\n[ÉXITO] Se extrajeron {len(nuevos_datos)} reseñas legítimas en bruto.")
        print(f"[INFO] Archivo generado con éxito en: '{self.archivo_salida}' ({len(datos_existentes)} elementos).")

    def extraer(self, url: str, asin: str, scrolls: int = 3):
        """
        Lanza el navegador automatizado con paginación integrada y unificada 
        tanto para Amazon como para Mercado Libre usando Playwright.

        'asin' es OBLIGATORIO: se usa para generar IDs de reseña únicos por
        producto y evitar que las reseñas de un producto sobrescriban las
        de otro en la base de datos (colisión de review_id).
        """
        print(f"\n🚀 Lanzando navegador automatizado para extracción específica...")
        asin_limpio = str(asin).strip().upper()
        reseñas_raspadas = []
        ruta_perfil = os.path.join(os.getcwd(), "sesion_playwright")

      # Bloqueamos inmediatamente cualquier intento de usar el truco 'userinfo'
        if "@" in url:
            print("⚠️ [SEGURIDAD] La URL contiene caracteres no permitidos ('@'). Operación abortada.")
            return []
            
        try:
            # Parseamos la URL para extraer el dominio real al que se dirige
            parsed_url = urllib.parse.urlparse(url)
            hostname = parsed_url.hostname.lower() if parsed_url.hostname else ""
        except Exception:
            print("⚠️ [ERROR] URL malformada.")
            return []

        # En lugar de buscar si la palabra está "en la url", validamos el Hostname real
        if "amazon." in hostname:
            plataforma = "amazon"
            print("📦 Plataforma validada de forma segura: AMAZON")
        elif "mercadolibre." in hostname:
            plataforma = "mercadolibre"
            print("💛 Plataforma validada de forma segura: MERCADO LIBRE")
        else:
            print("⚠️ [ERROR] URL no soportada o dominio inválido. Solo se permite Amazon y Mercado Libre.")
            return []
        # 👆 FIN DEL CAMBIO 1 👆
        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                user_data_dir=ruta_perfil,
                headless=False,
                viewport={"width": 1280, "height": 900},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                
                print("\n🔄 Esperando a que cargue la página de reseñas automáticamente...")
                print("⏳ [INFO] Tienes 3 MINUTOS para iniciar sesión o resolver el Captcha manualmente en la ventana...")
                
                try:
                    page.wait_for_selector('[data-hook="review"], .ui-review-capability-comments__comment, [class*="comment-container" i]', timeout=180000)
                    print("✅ Reseñas detectadas en pantalla. ¡Iniciando extracción por páginas!")
                    page.wait_for_timeout(2000) 
                except Exception:
                    print(f"❌ Tiempo agotado. Pasaron los 3 minutos y no se detectaron reseñas.")
                    return

                # --- BUCLE UNIFICADO DE PAGINACIÓN AUTOMÁTICA ---
                # El parámetro 'scrolls' ahora define el número de páginas que va a recorrer el robot
                for index_pagina in range(scrolls):
                    
                    # Si no es la primera página, disparamos el clic en el botón de navegación correspondiente
                    if index_pagina > 0:
                        boton_siguiente = None
                        
                        if plataforma == "amazon":
                            boton_siguiente = page.query_selector('.a-last a')
                        elif plataforma == "mercadolibre":
                            boton_siguiente = page.query_selector('.andes-pagination__button--next a, [title="Siguiente"]')

                        if boton_siguiente and boton_siguiente.is_visible():
                            print(f"➡️ [{plataforma.upper()}] Saltando automáticamente a la página {index_pagina + 1}...")
                            boton_siguiente.click()
                            
                            # Esperamos el selector de la nueva tanda dependiendo del sitio
                            selector_espera = '[data-hook="review"]' if plataforma == "amazon" else '.ui-review-capability-comments__comment, article'
                            page.wait_for_selector(selector_espera, timeout=25000)
                            page.wait_for_timeout(2000)
                        else:
                            print(f"[INFO] No se encontró el botón 'Siguiente' en la página {index_pagina}. Fin del catálogo.")
                            break

                    # Interacción específica interna por página
                    if plataforma == "mercadolibre":
                        print("[MERCADO LIBRE] Expandiendo textos ocultos 'Leer más' en el lote actual...")
                        try:
                            botones_leer_mas = page.query_selector_all('text="Leer más"')
                            for boton in botones_leer_mas:
                                if boton.is_visible():
                                    boton.click(timeout=1000)
                                    page.wait_for_timeout(1500)
                        except Exception:
                            pass
                    
                    # Un pequeño scroll hacia abajo por lote para activar cargas dinámicas secundarias en el DOM
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2);")
                    page.wait_for_timeout(1000)

                    # --- EVALUACIÓN DINÁMICA DEL DOM ---
                    print(f"[PROCESAMIENTO] Extrayendo lote de opiniones de la página {index_pagina + 1}...")
                    
                    if plataforma == "amazon":
                        script_extractor = """
                        () => {
                            let data = [];
                            let bloques = document.querySelectorAll('[data-hook="review"]');
                            let nodoProducto = document.querySelector('[data-hook="product-link"]');

                            let tituloProducto = nodoProducto 
                                ? nodoProducto.innerText.trim() 
                                : document.title.replace(/Amazon.*?:\s*Opiniones de clientes:\s*/i, "").trim();
                            
                            bloques.forEach((bloque, i) => {
                                let elAutor = bloque.querySelector('.a-profile-name');
                                let elTitulo = bloque.querySelector('[data-hook="review-title"]');
                                let elTexto = bloque.querySelector('[data-hook="review-body"]');
                                let elEstrellas = bloque.querySelector('.a-icon-alt');
                                
                                let elFecha = bloque.querySelector('[data-hook="review-date"]');
                                let elVariante = bloque.querySelector('[data-hook="format-strip"]');
                                let elVerificada = bloque.querySelector('[data-hook="avp-badge"]');

                                let autor = elAutor ? elAutor.innerText.trim() : "Comprador Anónimo";
                                let titulo = elTitulo ? elTitulo.innerText.trim() : "Opinión Extraída";
                                let texto = elTexto ? elTexto.innerText.trim() : "";
                                let fecha = elFecha ? elFecha.innerText.trim() : "Fecha desconocida";
                                let variante = elVariante ? elVariante.innerText.trim() : "Versión Estándar";
                                let verificada = elVerificada ? true : false;
                                
                                if (titulo.includes("de 5 estrellas")) {
                                    titulo = titulo.split("\\n").pop();
                                }

                                let estrellas = 5;
                                if (elEstrellas) {
                                    let match = elEstrellas.innerText.match(/([1-5])/);
                                    if (match) estrellas = parseInt(match[0]);
                                }

                                if (texto.length > 5) {
                                    data.push({
                                        "index": i,
                                        "producto": tituloProducto,
                                        "autor": autor,
                                        "titulo_comentario": titulo,
                                        "texto": texto,
                                        "estrellas": estrellas,
                                        "fecha_original": fecha,
                                        "variante": variante,
                                        "compra_verificada": verificada
                                    });
                                }
                            });
                            return data;
                        }
                        """
                    
                    elif plataforma == "mercadolibre":
                        script_extractor = """
                        () => {
                            let data = [];
                            let bloques = document.querySelectorAll('.ui-review-capability-comments__comment, [class*="comment-container" i], article');
                            let elTituloProd = document.querySelector('.ui-pdp-title, h1');
                            let tituloProducto = elTituloProd ? elTituloProd.innerText.trim() : "Producto Mercado Libre";

                            bloques.forEach((bloque, i) => {
                                let elTexto = bloque.querySelector('p, .ui-review-capability-comments__comment__content');
                                if (!elTexto) return;
                                
                                let texto = elTexto.innerText.trim();
                                
                                let estrellas = 5;
                                let elEstrellas = bloque.querySelector('[class*="rating" i], [aria-label*="estrellas" i]');
                                if (elEstrellas) {
                                    let label = elEstrellas.getAttribute('aria-label') || elEstrellas.innerText;
                                    let match = label.match(/([1-5])/);
                                    if (match) estrellas = parseInt(match[0]);
                                }

                                let autor = "Comprador de Mercado Libre";

                                if (texto.length > 5 && !texto.toUpperCase().includes("ÚTIL")) {
                                    data.push({
                                        "index": i,
                                        "producto": tituloProducto,
                                        "autor": autor,
                                        "titulo_comentario": "Opinión de Mercado Libre",
                                        "texto": texto,
                                        "estrellas": estrellas
                                    });
                                }
                            });
                            return data;
                        }
                        """

                    # Evaluamos e inyectamos el lote actual obtenido de esta página al arreglo global
                    opiniones_lote = page.evaluate(script_extractor)
                    
                    for op in opiniones_lote:
                        reseñas_raspadas.append({
                            "id": f"{asin_limpio}_{plataforma}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{index_pagina}_{op['index']}",
                            "asin": asin_limpio,
                            "producto": op.get("producto", "Producto Desconocido"),
                            "autor": "Comprador Anónimo",
                            "titulo_comentario": op["titulo_comentario"],
                            "texto": op["texto"],
                            "estrellas": op["estrellas"],
                            "variante": op.get("variante", ""),
                            "compra_verificada": op.get("compra_verificada", False),
                            "fuente": url,
                            "fecha_publicacion": op.get("fecha_original", "") 
                        })

                    # Pausa estratégica para evitar que los servidores nos identifiquen como ráfaga automatizada
                    page.wait_for_timeout(1500)

            except Exception as e:
                print(f"❌ Error crítico durante la extracción estructurada: {e}")
            finally:
                context.close()

        if reseñas_raspadas:
            self._guardar_json(reseñas_raspadas) # Tu código original
            print(f"🎉 Extracción masiva terminada. Catálogo finalizado con {len(reseñas_raspadas)} opiniones guardadas de forma unificada.")
            
            # 👇 AÑADE ESTA LÍNEA 👇
            return reseñas_raspadas
        else:
            print("⚠️ [ADVERTENCIA] No se capturaron reseñas. Asegúrate de estar parado en la página de comentarios completa.")
            # 👇 AÑADE ESTA LÍNEA 👇
            return []

if __name__ == "__main__":
    url_test = input("Ingresa URL de prueba (Amazon/MercadoLibre): ").strip()
    asin_test = input("Ingresa el ASIN del producto: ").strip()
    if url_test and asin_test:
        ex = ExtractorEspecifico()
        ex.extraer(url_test, asin_test)