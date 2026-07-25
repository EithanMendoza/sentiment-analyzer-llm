"""
Módulo de esquemas para la inferencia de IA.

Define la estructura de datos entrante para las consultas al motor RAG.
Contiene:
- PeticionMensaje: Valida el texto de la consulta del usuario y administra 
  el id_sesion para mantener el contexto de la conversación.
"""

from pydantic import BaseModel

class PeticionMensaje(BaseModel):
    id_sesion: str | None = None
    mensaje: str
