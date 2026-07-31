"""
Rutas públicas de autenticación y registro.

Expone los endpoints para crear nuevos usuarios en la base de datos
y para intercambiar credenciales válidas por un token JWT.
"""

import os
import asyncio
import httpx
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, status, Depends, Request
from fastapi.security import OAuth2PasswordRequestForm
from jose import jwt

# 1. Importamos la conexión de la base de datos
from modulos.base_datos.conexion import obtener_conexion

# 2. Importamos los esquemas de Pydantic
from modulos.api.schemas.auth import UsuarioRegistro, Token

# 3. Importamos las operaciones de base de datos
from modulos.base_datos.operaciones.usuarios import crear_usuario, obtener_usuario_por_correo

# 4. Importamos utilidades de seguridad reales, esquema OAuth2 y Rate Limiting
from modulos.seguridad.autenticacion import (
    obtener_hash_password,
    verificar_password,
    crear_token_acceso,
    esquema_oauth2,
    PUBLIC_KEY,
    ALGORITHM
)
from slowapi import Limiter
from slowapi.util import get_remote_address

router = APIRouter()

# Se inicializa el limitador local para mapear por IP del cliente
REDIS_URL = os.getenv("REDIS_URL", "memory://")
limiter = Limiter(key_func=get_remote_address, storage_uri=REDIS_URL)

# 🔐 CLAVE SECRETA DE CLOUDFLARE TURNSTILE
# Se extrae de forma segura de las variables de entorno. 
# Si no se encuentra, usa tu Secret Key real provista como fallback secundario.
TURNSTILE_SECRET = os.getenv("TURNSTILE_SECRET_KEY", "0x4AAAAAAD_uOvS5o03zJR6vtBmyUwnomlE")

async def verificar_token_cloudflare(token: str) -> bool:
    """
    Envía el token a Cloudflare para verificar que fue generado por un humano.
    """
    url = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
    payload = {
        "secret": TURNSTILE_SECRET,
        "response": token
    }
    
    async with httpx.AsyncClient() as client:
        try:
            respuesta = await client.post(url, data=payload, timeout=5.0)
            datos = respuesta.json()
            return datos.get("success", False)
        except Exception as e:
            print(f"[ERROR TURNSTILE]: {e}")
            # Si Cloudflare está caído o hay un error de red, asumimos falso por seguridad
            return False


@router.post("/registro", status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")  # Limita a 5 registros por minuto por IP
async def registrar_usuario(
    request: Request,  # 👈 Requerido internamente por SlowAPI de forma transparente
    usuario: UsuarioRegistro
):
    """
    Recibe los datos del usuario, encripta la contraseña y guarda el registro en SQLite.
    Protegido contra ataques de automatización y creación de cuentas masivas (Máximo 5 por minuto).
    """

    # 1. VALIDACIÓN DEL CAPTCHA ANTES DE HACER CUALQUIER OTRA COSA
    es_humano = await verificar_token_cloudflare(usuario.captcha_token)
    if not es_humano:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Validación de seguridad fallida. Por favor, intenta de nuevo."
        )
    
    # Hasheamos la contraseña real con bcrypt
    hash_pw = obtener_hash_password(usuario.password)
    
    # Insertamos en la BD usando un hilo separado para no bloquear el servidor
    nuevo_id = await asyncio.to_thread(
        crear_usuario, 
        usuario.first_name,
        usuario.last_name,
        usuario.email, 
        hash_pw
    )
    
    if not nuevo_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El correo ya está registrado."
        )
    return {"mensaje": "Usuario creado exitosamente", "id": nuevo_id}


@router.post("/login", response_model=Token)
@limiter.limit("5/minute")
async def iniciar_sesion(
    request: Request
):
    """
    Verifica las credenciales y devuelve un token JWT válido por 2 horas.
    Protegido contra ataques de fuerza bruta.
    Estandarizado (A-04): Utiliza estrictamente 'email' y 'password'.
    """
    
    # 1. Detectar el Content-Type para unificar JSON y Form-Urlencoded
    content_type = request.headers.get("content-type", "")
    
    if "application/json" in content_type:
        try:
            cuerpo = await request.json()
            # 🔄 A-04: Estandarizado estrictamente a 'email' y 'password'
            email = cuerpo.get("email")
            password = cuerpo.get("password")
        except Exception:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="JSON inválido")
    else:
        # 2. Fallback al estándar OAuth2 (formulario tradicional)
        formulario = await request.form()
        email = formulario.get("username") or formulario.get("email")
        password = formulario.get("password")
        
    if not email or not password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Faltan credenciales (email y password son requeridos)"
        )

    # 👇 LÍNEAS TEMPORALES DE DEBUGEU DE IP 👇
    ip_cabecera = request.headers.get("X-Forwarded-For", "No existe")
    ip_detectada = request.client.host
    print(f"\n[DEBUG SEGURIDAD] X-Forwarded-For: {ip_cabecera} | IP Cliente (FastAPI): {ip_detectada}\n")
    # 👆 HASTA AQUÍ 👆

    # Buscamos al usuario por correo en la BD[cite: 6]
    usuario_db = await asyncio.to_thread(obtener_usuario_por_correo, email)
    
    # Verificamos que el usuario exista y que la contraseña coincida con el hash
    if not usuario_db or not verificar_password(password, usuario_db["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Correo o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # 👇 MITIGACIÓN PII APLICADA 👇
    # Generamos el token JWT inyectando ÚNICAMENTE el identificador.
    # Eliminamos por completo email, first_name y last_name del payload.
    token_jwt = crear_token_acceso(data={
        "sub": usuario_db["id"]
    })
    
    return {"access_token": token_jwt, "token_type": "bearer"}


@router.post("/logout", status_code=status.HTTP_200_OK)
@limiter.limit("5/minute")
async def cerrar_sesion(
    request: Request,
    token: str = Depends(esquema_oauth2)
):
    """
    Invalida el token JWT del usuario actual añadiéndolo a la lista negra en la BD.
    Evita que tokens robados sigan siendo utilizables.
    """
    try:
        # Extraemos la fecha de expiración real del token para optimizar la limpieza futura
        payload = jwt.decode(token, PUBLIC_KEY, algorithms=[ALGORITHM])
        exp_timestamp = payload.get("exp")
        
        if exp_timestamp:
            expiracion = datetime.fromtimestamp(exp_timestamp, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        else:
            expiracion = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            
        def revocar_token():
            conn = obtener_conexion()
            c = conn.cursor()
            c.execute('''
                INSERT OR IGNORE INTO jwt_blacklist (token, expiracion)
                VALUES (?, ?)
            ''', (str(token), expiracion))
            conn.commit()
            conn.close()

        await asyncio.to_thread(revocar_token)
        return {"status": "success", "mensaje": "Sesión cerrada exitosamente."}
        
    except Exception as e:
        print(f"[ERROR LOGOUT ENDPOINT]: {e}")
        # Retornamos éxito simulado para evitar confirmación de ataques por denegación de logs
        return {"status": "success", "mensaje": "Sesión cerrada."}