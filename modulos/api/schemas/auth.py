"""
Módulo de esquemas de autenticación.

Define los modelos de datos (Pydantic) requeridos para el registro de nuevos
usuarios, el login y la generación de tokens de acceso.
Contiene:
- UsuarioRegistro: Valida nombre, apellido, correo y contraseña.
- UsuarioLogin: Valida credenciales de acceso (NUEVO - filtra inputs maliciosos/malformados).
- Token: Estructura legacy del token JWT (ya no se usa en la respuesta de /login).
- SesionUsuario: Respuesta de /login. Ya NO incluye el JWT (viaja en cookie HttpOnly).
"""

from pydantic import BaseModel, EmailStr, constr
from typing import Optional


class UsuarioRegistro(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr  # o simplemente str si no usas EmailStr
    password: str
    captcha_token: str  # Captcha token para validación del frontend


class UsuarioLogin(BaseModel):
    """
    Tipos estrictos para /login. Al declarar email como EmailStr y password
    como constr(...), FastAPI rechaza automáticamente (422) cualquier payload
    con tipos incorrectos, campos extra inesperados o estructuras anómalas
    (por ejemplo dicts/listas donde se espera un string), antes de que ese
    dato llegue a tocar la capa de base de datos.
    """
    email: EmailStr
    password: constr(min_length=1, max_length=128)


class Token(BaseModel):
    """Se mantiene por compatibilidad, pero /login ya no la usa como response_model."""
    access_token: str
    token_type: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None


class SesionUsuario(BaseModel):
    """
    Respuesta real de /login y de /me. El JWT ya no va aquí (va en la cookie
    HttpOnly). Incluye 'id' para que el frontend deje de decodificar el JWT
    manualmente con atob() para sacar el identificador del usuario.
    """
    id: Optional[str] = None
    token_type: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None