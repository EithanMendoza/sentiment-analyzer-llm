import os
from dotenv import load_dotenv
from modulos.extractor.apify_client import ExtractorAmazonReef

# Cargar el token desde el archivo .env
load_dotenv()

def probar_api():
    token = os.getenv("APIFY_TOKEN")
    if not token:
        print("❌ Error: No se encontró APIFY_TOKEN. ¿Creaste el archivo .env?")
        return

    # Inicializamos el extractor
    extractor = ExtractorAmazonReef(api_token=token)
    
    # Probamos con un ASIN
    resultados = extractor.extraer_y_limpiar(asin="B0CYWFH5Y9", marketplace="com.mx")
    
    if resultados:
        print("\n--- MUESTRA DE LA PRIMERA RESEÑA LIMPIA ---")
        print(f"Título: {resultados[0].get('title')}")
        print(f"Texto: {resultados[0].get('body')}")
        print("-------------------------------------------")

if __name__ == "__main__":
    probar_api()