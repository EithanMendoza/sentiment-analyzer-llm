"""
Rutas públicas de autenticación y registro.

Expone los endpoints para crear nuevos usuarios en la base de datos
y para intercambiar credenciales válidas por un token JWT.
"""

import asyncio
from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.security import OAuth2PasswordRequestForm

# 1. Importamos los esquemas de Pydantic
from modulos.api.schemas.auth import UsuarioRegistro, Token

# 2. Importamos las operaciones de base de datos
from modulos.base_datos.operaciones.usuarios import crear_usuario, obtener_usuario_por_correo

# 3. Importamos tus utilidades de seguridad reales
from modulos.seguridad.autenticacion import (
    obtener_hash_password,
    verificar_password,
    crear_token_acceso
)

router = APIRouter()

@router.post("/registro", status_code=status.HTTP_201_CREATED)
async def registrar_usuario(usuario: UsuarioRegistro):
    """
    Recibe los datos del usuario, encripta la contraseña y guarda el registro en SQLite.
    """
    # Hasheamos la contraseña real con bcrypt
    hash_pw = obtener_hash_password(usuario.contrasena)
    
    # Insertamos en la BD usando un hilo separado para no bloquear el servidor
    nuevo_id = await asyncio.to_thread(
        crear_usuario, 
        usuario.nombre,
        usuario.apellido,
        usuario.correo, 
        hash_pw
    )
    
    if not nuevo_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El correo ya está registrado."
        )
    return {"mensaje": "Usuario creado exitosamente", "id": nuevo_id}

@router.post("/login", response_model=Token)
async def iniciar_sesion(credenciales: OAuth2PasswordRequestForm = Depends()):
    """
    Verifica las credenciales y devuelve un token JWT válido por 2 horas.
    """
    # Buscamos al usuario por correo en la BD
    usuario_db = await asyncio.to_thread(obtener_usuario_por_correo, credenciales.username)
    
    # Verificamos que el usuario exista y que la contraseña coincida con el hash
    if not usuario_db or not verificar_password(credenciales.password, usuario_db["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Correo o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Generamos el token JWT inyectando el ID del usuario como 'sub'
    token_jwt = crear_token_acceso(data={"sub": usuario_db["id"]})
    
    return {"access_token": token_jwt, "token_type": "bearer"}