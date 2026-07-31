"""
Módulo de esquemas de autenticación.

Define los modelos de datos (Pydantic) requeridos para el registro de nuevos
usuarios y la generación de tokens de acceso. 
Contiene:
- UsuarioRegistro: Valida nombre, apellido, correo y contraseña.
- Token: Estructura del token JWT de respuesta.
"""

from pydantic import BaseModel, EmailStr
from typing import Optional

class UsuarioRegistro(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr  # o simplemente str si no usas EmailStr
    password: str
    captcha_token: str  # Captcha token para validación del frontend

class Token(BaseModel):
    access_token: str
    token_type: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None