import os
from fastapi import Request
from slowapi import Limiter

def obtener_ip_cliente_segura(request: Request) -> str:
    """
    Estrategia estricta solicitada por la auditoría (Ronda 8 - REV-2026-R8-01).
    Calcula el rate-limit estrictamente sobre la IP real del socket de conexión
    para evitar por completo el bypass por rotación/falsificación de la cabecera X-Forwarded-For.
    """
    # 🛡️ MITIGACIÓN CRÍTICA: Ignorar cabeceras X-Forwarded-For inyectables por el cliente.
    # Se utiliza request.client.host para evaluar la IP real de la conexión establecida del socket.
    if request.client and request.client.host:
        return request.client.host
        
    return "127.0.0.1"

REDIS_URL = os.getenv("REDIS_URL", "memory://")
limiter = Limiter(
    key_func=obtener_ip_cliente_segura, 
    storage_uri=REDIS_URL
)