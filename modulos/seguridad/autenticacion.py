import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from fastapi import Cookie, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from modulos.base_datos.conexion import obtener_conexion

# Cargar las variables de entorno desde el archivo .env
load_dotenv()

# =====================================================================
# CONFIGURACIÓN DE SEGURIDAD BLINDADA (RS256)
# =====================================================================
PRIVATE_KEY = os.getenv("JWT_PRIVATE_KEY", "").replace("\\n", "\n")
PUBLIC_KEY = os.getenv("JWT_PUBLIC_KEY", "").replace("\\n", "\n")

ALGORITHM = "RS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 120  # El token expira en 2 horas

if not PRIVATE_KEY or not PUBLIC_KEY:
    print("[ADVERTENCIA] Faltan las llaves RSA para firmar/verificar JWT. El login fallará.")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# =====================================================================
# FUNCIONES DE HASHEO DE CONTRASEÑAS
# =====================================================================
def obtener_hash_password(password: str) -> str:
    """Toma una contraseña en texto plano y devuelve un hash irreversible."""
    return pwd_context.hash(password)


def verificar_password(plain_password: str, hashed_password: str) -> bool:
    """Compara una contraseña en texto plano con el hash guardado en la BD."""
    return pwd_context.verify(plain_password, hashed_password)


# =====================================================================
# GENERACIÓN DE TOKENS JWT
# =====================================================================
def crear_token_acceso(data: dict) -> str:
    """
    Recibe un diccionario, extrae estrictamente el identificador y
    devuelve un token JWT firmado, eliminando cualquier PII.
    """
    usuario_id = data.get("sub")

    if not usuario_id:
        raise ValueError("El identificador 'sub' es obligatorio para generar el token.")

    to_encode = {"sub": str(usuario_id)}
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})

    encoded_jwt = jwt.encode(to_encode, PRIVATE_KEY, algorithm=ALGORITHM)
    return encoded_jwt


# =====================================================================
# ESQUEMAS DE EXTRACCIÓN DE TOKEN
# =====================================================================
# Se conserva solo para que /docs siga mostrando el flujo OAuth2 en Swagger
# (tokenUrl informativo). Ya NO se usa como dependencia real de las rutas
# protegidas: el JWT viaja en una cookie HttpOnly, no en el header Authorization.
esquema_oauth2 = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def obtener_token_cookie(access_token: str = Cookie(default=None)) -> str:
    """
    Extrae el JWT desde la cookie HttpOnly 'access_token'.
    Reemplaza al header 'Authorization: Bearer' como fuente del token,
    para que el JWT nunca sea accesible desde JavaScript (mitigación XSS).
    """
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No autenticado.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return access_token


# =====================================================================
# DEPENDENCIA DE VALIDACIÓN DE SESIÓN (EL GUARDIA)
# =====================================================================
def obtener_usuario_actual(token: str = Depends(obtener_token_cookie)):
    """
    Función Guardia: Intercepta el Token (ahora desde la cookie), comprueba
    la lista negra, lo desencripta y verifica si es válido.
    """
    excepcion_credenciales = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se pudieron validar las credenciales o el token ha expirado.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        conn = obtener_conexion()
        c = conn.cursor()
        c.execute('SELECT token FROM jwt_blacklist WHERE token = ?', (str(token),))
        token_revocado = c.fetchone()
        conn.close()

        if token_revocado:
            raise excepcion_credenciales
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"[ERROR CHECK BLACKLIST]: {e}")
        raise excepcion_credenciales

    try:
        payload = jwt.decode(token, PUBLIC_KEY, algorithms=[ALGORITHM])
        usuario_id: str = payload.get("sub")
        if usuario_id is None:
            raise excepcion_credenciales
        return usuario_id
    except JWTError:
        raise excepcion_credenciales