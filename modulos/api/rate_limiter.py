import os
from fastapi import Request
from slowapi import Limiter

def obtener_ip_cliente_segura(request: Request) -> str:
    """
    Estrategia defensiva para extraer la IP real del cliente.
    """
    ip_cloudflare = request.headers.get("CF-Connecting-IP")
    if ip_cloudflare:
        return ip_cloudflare.strip()
        
    if request.client and request.client.host:
        return request.client.host
        
    return "127.0.0.1"

# Inicialización ÚNICA y global
REDIS_URL = os.getenv("REDIS_URL", "memory://")
limiter = Limiter(
    key_func=obtener_ip_cliente_segura, 
    storage_uri=REDIS_URL
)