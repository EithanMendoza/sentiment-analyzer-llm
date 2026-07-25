"""
Traductor de contextos para el framework de IA.
"""
from llama_index.core.llms import ChatMessage, MessageRole
from operaciones.sesiones import obtener_historial_crudo

def cargar_historial(sesion_id: str):
    """Recupera el historial y lo formatea para LlamaIndex."""
    filas = obtener_historial_crudo(sesion_id)
    
    historial = []
    for rol, contenido in filas:
        if rol == 'user':
            historial.append(ChatMessage(role=MessageRole.USER, content=contenido))
        elif rol == 'assistant':
            historial.append(ChatMessage(role=MessageRole.ASSISTANT, content=contenido))
            
    return historial