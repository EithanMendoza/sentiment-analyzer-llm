from pydantic import BaseModel, Field

class SolicitudLimpiezaCache(BaseModel):
    confirmar_borrado: bool = Field(..., description="Debe ser true para proceder con el vaciado.")
    frase_confirmacion: str = Field(..., description="Debe coincidir exactamente con 'ELIMINAR'")