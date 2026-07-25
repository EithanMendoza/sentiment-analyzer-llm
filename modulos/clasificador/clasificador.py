from datetime import datetime
import json
import os
import re
import time
from llama_index.llms.ollama import Ollama
import asyncio 

class ClasificadorReseñas:
    # Por defecto usamos el modelo optimizado que configuramos
    def __init__(self, modelo="qwen2.5:1.5b"):
        self.llm = Ollama(
            model=modelo, 
            request_timeout=120.0, 
            additional_kwargs={"format": "json"}
        )

    def _generar_prompt(self, titulo: str, cuerpo: str) -> str:
        """Genera un prompt estructurado bajo formato Few-Shot para Qwen."""
        return f"""
Analiza la siguiente opinión de un comprador para determinar su sentimiento y su categoría analítica precisa.

DATOS DE LA OPINIÓN:
- Título/Asunto: "{titulo}"
- Comentario Completo: "{cuerpo}"

INSTRUCCIONES DE CLASIFICACIÓN:
1. "sentimiento": Debe ser únicamente uno de estos dos valores: "Positivo" o "Negativo". Fuerza la decisión basándote en el balance del texto.
2. "categoria": Identifica el núcleo temático principal. Valores específicos válidos:
   - "Rendimiento y Caídas" (Bugs, congelamientos, lentitud, fallas de hardware/software).
   - "Diseño e Interfaz" (Estética, color, comodidad, ergonomía, acabados visuales).
   - "Materiales y Durabilidad" (Calidad de plásticos, resistencia a golpes, desgaste).
   - "Logística y Envío" (Tiempos de entrega, retrasos, paquetería).
   - "Embalaje del Producto" (Estado de la caja original, sellos rotos, falta de accesorios).
   - "Precio y Valor" (Relación calidad-precio, costo, si vale la pena la inversión).
   - "Soporte Técnico" (Atención al cliente, garantías, cambios, devoluciones).
   - "Funcionalidad" (Si cumple con las características básicas prometidas en la descripción).
   - "General" (Opiniones ambiguas, vacías o extremadamente cortas).

RESTRICCIÓN ABSOLUTA:
Devuelve EXCLUSIVAMENTE un objeto JSON válido con las llaves "sentimiento" y "categoria". No agregues texto adicional.

EJEMPLO DE SALIDA ESTRICTA:
{{"sentimiento": "Negativo", "categoria": "Rendimiento y Caídas"}}
""".strip()

    def _limpiar_y_parsear_json(self, texto_crudo: str) -> dict:
        """Aisla el objeto JSON puro y lo parsea de forma segura."""
        texto_limpio = texto_crudo.strip()
        
        texto_limpio = re.sub(r"^```json\s*", "", texto_limpio, flags=re.IGNORECASE)
        texto_limpio = re.sub(r"^```\s*", "", texto_limpio, flags=re.IGNORECASE)
        texto_limpio = re.sub(r"\s*```$", "", texto_limpio, flags=re.IGNORECASE)
        texto_limpio = texto_limpio.strip()
        
        match = re.search(r'\{.*\}', texto_limpio, re.DOTALL)
        if match:
            texto_limpio = match.group(0)
            
        return json.loads(texto_limpio)

    async def clasificar_reseña_con_reintentos(self, titulo: str, texto: str, estrellas_originales: any, max_reintentos: int = 3) -> dict:
        """Intenta clasificar una reseña de forma asíncrona mitigando caídas de Ollama."""
        prompt = self._generar_prompt(titulo, texto)
        
        categorias_validas = {
            "Rendimiento y Caídas", "Diseño e Interfaz", "Materiales y Durabilidad",
            "Logística y Envío", "Embalaje del Producto", "Precio y Valor", 
            "Soporte Técnico", "Funcionalidad", "General"
        }
        
        try:
            num_estrellas = int(estrellas_originales) if estrellas_originales is not None else 5
        except:
            num_estrellas = 5

        for intento in range(max_reintentos):
            try:
                respuesta_raw = await self.llm.acomplete(prompt)
                respuesta = respuesta_raw.text
                datos_ia = self._limpiar_y_parsear_json(respuesta)
                
                if "sentimiento" in datos_ia and "categoria" in datos_ia:
                    sentimiento = str(datos_ia["sentimiento"]).strip().capitalize()
                    categoria = str(datos_ia["categoria"]).strip()
                    
                    categoria_corregida = next(
                        (c for c in categorias_validas if c.lower() == categoria.lower()), 
                        "General"
                    )
                    
                    # 🚨 Respaldo 1: Si la IA alucina otra opción, aplicamos tu regla: 1-2 Negativo, 3+ Positivo
                    if sentimiento not in ["Positivo", "Negativo"]:
                        sentimiento = "Negativo" if num_estrellas <= 2 else "Positivo"
                        
                    return {"sentimiento": sentimiento, "categoria": categoria_corregida}
                raise KeyError("Estructura JSON incompleta.")
            except Exception as e:
                print(f"[REINTENTO ASYNC] {intento + 1}/{max_reintentos} fallido. [Error: {e}]")
                await asyncio.sleep(1)
                
        raise RuntimeError("Inferencia asíncrona fallida tras reintentos continuos.")

    # Cambia esta línea:
    # async def procesar_pipeline(self, archivo_entrada="reseñas_crudas.json", archivo_salida="reseñas_enriquecidas.json"):
    
    # Por esta:
    async def procesar_pipeline(self, archivo_entrada="datos/reseñas_crudas.json", archivo_salida="datos/reseñas_enriquecidas.json"):
        """Estructura y enriquece el dataset en paralelo con asyncio.gather."""
        if not os.path.exists(archivo_entrada):
            print(f"[ERROR CRÍTICO] No existe el archivo '{archivo_entrada}'.")
            return

        with open(archivo_entrada, "r", encoding="utf-8") as f:
            reseñas_crudas = json.load(f)

        print(f"[OLLAMA PARALELO] Creando tareas concurrentes para {len(reseñas_crudas)} reseñas...")
        
        async def procesar_individual(index, item):
            autor = item.get("autor", "Anónimo")
            titulo = item.get("titulo_comentario", "Sin título")
            cuerpo_texto = item.get("texto", "")
            estrellas_raw = item.get("estrellas", None)
            
            try:
                # Pasamos las estrellas para la lógica de control interna
                datos_ia = await self.clasificar_reseña_con_reintentos(titulo, cuerpo_texto, estrellas_raw)
                sentimiento_final = datos_ia["sentimiento"]
                categoria_final = datos_ia["categoria"]
            except Exception:
                # 🚨 Respaldo 2: Fallo seguro absoluto si Ollama se desconecta por completo
                try:
                    estrellas_int = int(estrellas_raw) if estrellas_raw is not None else 5
                except:
                    estrellas_int = 5
                sentimiento_final = "Negativo" if estrellas_int <= 2 else "Positivo"
                categoria_final = "General"

            id_final = item.get("id", item.get("id_origen", f"local_{index}"))
            fecha_final = item.get("fecha_publicacion", datetime.now().strftime("%Y-%m-%d"))

            return {
                "id": id_final,
                "producto": item.get("producto", "Producto Desconocido"),
                "autor": autor,
                "titulo_comentario": titulo,
                "texto": cuerpo_texto,
                "estrellas": estrellas_raw,
                "fuente": item.get("fuente", "Desconocida"),
                "variante": item.get("variante", ""),                     
                "compra_verificada": item.get("compra_verificada", False),
                "metadatos": {
                    "sentimiento": sentimiento_final,
                    "categoria": categoria_final,
                    "fecha_publicacion": fecha_final
                }
            }

        tareas = [procesar_individual(i, item) for i, item in enumerate(reseñas_crudas)]
        reseñas_enriquecidas = await asyncio.gather(*tareas)

        with open(archivo_salida, "w", encoding="utf-8") as f:
            json.dump(reseñas_enriquecidas, f, ensure_ascii=False, indent=4)
            
        print(f"\n[PIPELINE COMPLETADO] Dataset enriquecido guardado en: '{archivo_salida}'")

if __name__ == "__main__":
    analizador = ClasificadorReseñas()
    # Ejecución correcta para pruebas directas desde terminal
    asyncio.run(analizador.procesar_pipeline())