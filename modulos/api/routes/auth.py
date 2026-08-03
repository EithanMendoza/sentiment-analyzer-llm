"""
Rutas públicas de autenticación y registro.

Expone los endpoints para crear nuevos usuarios en la base de datos
y para intercambiar credenciales válidas por un token JWT (entregado
como cookie HttpOnly).
"""

import os
import asyncio
import httpx
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, status, Depends, Request, Response
from jose import jwt
from pydantic import ValidationError

# 1. Importamos la conexión de la base de datos
from modulos.base_datos.conexion import obtener_conexion

# 2. Importamos los esquemas de Pydantic
from modulos.api.schemas.auth import UsuarioRegistro, UsuarioLogin, SesionUsuario

# 3. Importamos las operaciones de base de datos
from modulos.base_datos.operaciones.usuarios import (
    crear_usuario,
    obtener_usuario_por_correo,
    obtener_usuario_por_id,
)

# 4. Importamos utilidades de seguridad reales y Rate Limiting
from modulos.seguridad.autenticacion import (
    obtener_hash_password,
    verificar_password,
    crear_token_acceso,
    obtener_token_cookie,
    obtener_usuario_actual,
    PUBLIC_KEY,
    ALGORITHM
)
from modulos.api.rate_limiter import limiter
router = APIRouter()

# 🔐 CLAVE SECRETA DE CLOUDFLARE TURNSTILE
TURNSTILE_SECRET = os.getenv("TURNSTILE_SECRET_KEY", "0x4AAAAAAD_uOvS5o03zJR6vtBmyUwnomlE")

# 🍪 Configuración de la cookie de sesión
COOKIE_NAME = "access_token"
COOKIE_MAX_AGE = 60 * 60 * 2  # 2 horas — igual que ACCESS_TOKEN_EXPIRE_MINUTES
# En local (sin HTTPS) "Secure" bloquearía la cookie; en producción debe ir en True.
COOKIE_SECURE = os.getenv("ENTORNO", "produccion").lower() != "desarrollo"


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
            return False


@router.post("/registro", status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def registrar_usuario(
    request: Request,
    usuario: UsuarioRegistro
):
    """
    Recibe los datos del usuario, encripta la contraseña y guarda el registro en SQLite.
    Protegido contra ataques de automatización y creación de cuentas masivas (Máximo 5 por minuto).
    """
    es_humano = await verificar_token_cloudflare(usuario.captcha_token)
    if not es_humano:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Validación de seguridad fallida. Por favor, intenta de nuevo."
        )

    hash_pw = obtener_hash_password(usuario.password)

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


@router.post("/login", response_model=SesionUsuario)
@limiter.limit("5/minute")
async def iniciar_sesion(
    request: Request,
    response: Response,
    credenciales: UsuarioLogin  # 👈 ¡ESTA ES LA MAGIA! Al ponerlo aquí, Swagger ya sabe qué pedir.
):
    """
    Verifica las credenciales y entrega el JWT en una cookie HttpOnly válida por 2 horas.
    Protegido contra ataques de fuerza bruta y NoSQLi mediante validación estricta de Pydantic.
    """
    
    # Al usar 'credenciales: UsuarioLogin', FastAPI ya hizo la validación por nosotros.
    # Si mandan objetos raros o inyecciones, FastAPI lanza el error 422 automáticamente.
    email = credenciales.email
    password = credenciales.password

    # 👇 LÍNEAS TEMPORALES DE DEBUG DE IP 👇
    ip_cabecera = request.headers.get("X-Forwarded-For", "No existe")
    ip_detectada = request.client.host
    print(f"\n[DEBUG SEGURIDAD] X-Forwarded-For: {ip_cabecera} | IP Cliente (FastAPI): {ip_detectada}\n")
    # 👆 HASTA AQUÍ 👆

    usuario_db = await asyncio.to_thread(obtener_usuario_por_correo, email)

    if not usuario_db or not verificar_password(password, usuario_db["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Correo o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Token JWT estrictamente blindado (solo lleva el identificador 'sub')
    token_jwt = crear_token_acceso(data={
        "sub": usuario_db["id"]
    })

    # 🍪 MITIGACIÓN XSS: el JWT viaja en una cookie HttpOnly
    response.set_cookie(
        key=COOKIE_NAME,
        value=token_jwt,
        httponly=True,
        secure=COOKIE_SECURE, 
        samesite="none",      
        max_age=COOKIE_MAX_AGE,
        path="/",
    )

    return {
        "id": usuario_db["id"],
        "token_type": "bearer",
        "first_name": usuario_db["nombre"],
        "last_name": usuario_db["apellido"],
        "email": usuario_db["correo"]
    }


@router.get("/me", response_model=SesionUsuario)
async def usuario_actual(usuario_id: str = Depends(obtener_usuario_actual)):
    """
    El frontend llama esto al cargar la app para saber si la cookie sigue
    siendo válida (JS no puede leer el JWT directamente, así que este es
    el único modo de confirmar sesión activa tras un refresh).
    """
    usuario_db = await asyncio.to_thread(obtener_usuario_por_id, usuario_id)
    if not usuario_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")

    return {
        "id": usuario_db["id"],
        "first_name": usuario_db["nombre"],
        "last_name": usuario_db["apellido"],
        "email": usuario_db["correo"]
    }


@router.post("/logout", status_code=status.HTTP_200_OK)
@limiter.limit("5/minute")
async def cerrar_sesion(
    request: Request,
    response: Response
):
    """
    Invalida el token JWT del usuario actual añadiéndolo a la lista negra en la BD
    y borra la cookie de sesión en el navegador incondicionalmente.
    """
    # 1. Intentamos recuperar el token de las cookies manualmente para no bloquear la ejecución
    token = request.cookies.get(COOKIE_NAME)
    
    if token and token.startswith("Bearer "):
        token = token.split(" ")[1]

    if token:
        try:
            # options={"verify_exp": False} asegura que si el token ya expiró, igual lo podamos añadir a la blacklist
            payload = jwt.decode(token, PUBLIC_KEY, algorithms=[ALGORITHM], options={"verify_exp": False})
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
        except Exception as e:
            print(f"[ERROR LOGOUT ENDPOINT]: {e}")
            
    # 2. 🍪 Borramos la cookie siempre, garantizando que el navegador cierre la sesión
    response.delete_cookie(
        key=COOKIE_NAME,
        path="/",
        httponly=True,
        samesite="none",
        secure=COOKIE_SECURE
    )
    
    return {"status": "success", "mensaje": "Sesión cerrada exitosamente."}