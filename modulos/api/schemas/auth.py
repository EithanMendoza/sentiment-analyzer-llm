"""
Módulo de esquemas de autenticación.

Define los modelos de datos (Pydantic) requeridos para el registro de nuevos
usuarios y la generación de tokens de acceso. 
Contiene:
- UsuarioRegistro: Valida nombre, apellido, correo y contraseña.
- Token: Estructura del token JWT de respuesta.
"""

from pydantic import BaseModel, EmailStr

class UsuarioRegistro(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr  # o simplemente str si no usas EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str