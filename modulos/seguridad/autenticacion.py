import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from modulos.base_datos.conexion import obtener_conexion

# Cargar las variables de entorno desde el archivo .env
load_dotenv()

# =====================================================================
# CONFIGURACIÓN DE SEGURIDAD BLINDADA (RS256)
# =====================================================================
# Cargamos las llaves asimétricas. El .replace("\\n", "\n") es vital porque 
# a menudo los archivos .env leen los saltos de línea como texto literal.
PRIVATE_KEY = os.getenv("JWT_PRIVATE_KEY", "").replace("\\n", "\n")
PUBLIC_KEY = os.getenv("JWT_PUBLIC_KEY", "").replace("\\n", "\n")

# Cambiamos explícitamente a RS256
ALGORITHM = "RS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 120  # El token expira en 2 horas

# Verificación de seguridad al arranque
if not PRIVATE_KEY or not PUBLIC_KEY:
    print("[ADVERTENCIA] Faltan las llaves RSA para firmar/verificar JWT. El login fallará.")

# Configuración del algoritmo de encriptación (bcrypt)
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
    # 1. Extraemos SOLO el ID del usuario
    usuario_id = data.get("sub")
    
    if not usuario_id:
        raise ValueError("El identificador 'sub' es obligatorio para generar el token.")

    # 🔒 MITIGACIÓN PII: Armamos un diccionario nuevo explícitamente.
    # Cualquier otro dato como 'nombre', 'apellido' o 'email' será ignorado.
    to_encode = {"sub": str(usuario_id)}
    
    # 2. Agregamos la expiración
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    
    # 3. Firmamos el token
    encoded_jwt = jwt.encode(to_encode, PRIVATE_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# =====================================================================
# DEPENDENCIA DE VALIDACIÓN DE SESIÓN (EL GUARDIA)
# =====================================================================
esquema_oauth2 = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

def obtener_usuario_actual(token: str = Depends(esquema_oauth2)):
    """
    Función Guardia: Intercepta el Token, comprueba la lista negra, 
    lo desencripta y verifica si es válido.
    """
    excepcion_credenciales = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se pudieron validar las credenciales o el token ha expirado.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    # 🚀 VERIFICACIÓN DE LISTA NEGRA: Validamos si el token fue revocado por Logout
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
        # 👇 VERIFICACIÓN USANDO LA LLAVE PÚBLICA
        payload = jwt.decode(token, PUBLIC_KEY, algorithms=[ALGORITHM])
        usuario_id: str = payload.get("sub")
        if usuario_id is None:
            raise excepcion_credenciales
        return usuario_id
    except JWTError:
        raise excepcion_credenciales