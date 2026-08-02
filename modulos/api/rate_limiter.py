import os
from fastapi import Request
from slowapi import Limiter

def obtener_ip_cliente_segura(request: Request) -> str:
    """
    Estrategia defensiva para extraer la IP real detrás de proxies como Render/ngrok.
    """
    # 1. Intentamos leer la cabecera estándar de proxies
    x_forwarded_for = request.headers.get("X-Forwarded-For")
    
    if x_forwarded_for:
        # El atacante puede falsificar el inicio, pero el proxy (Render/ngrok) 
        # SIEMPRE añade la IP real de forma segura al final de la lista.
        ips = [ip.strip() for ip in x_forwarded_for.split(",")]
        return ips[-1] # Tomamos la última IP, que es la confiable
        
    # 2. Si no hay proxy (ej. desarrollo local directo), usamos la conexión
    if request.client and request.client.host:
        return request.client.host
        
    return "127.0.0.1"

REDIS_URL = os.getenv("REDIS_URL", "memory://")
limiter = Limiter(
    key_func=obtener_ip_cliente_segura, 
    storage_uri=REDIS_URL
)