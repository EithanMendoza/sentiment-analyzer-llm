"""
Esquema inicial de la base de datos.
"""
from .conexion import obtener_conexion

def inicializar_base_datos():
    """
    Inicializa el esquema relacional para soporte SaaS multiusuario.
    Crea las tablas: usuarios, sesiones, mensajes y auditoria.
    """
    conn = obtener_conexion()
    c = conn.cursor()

    # 1. TABLA: Usuarios
    c.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id TEXT PRIMARY KEY,
            nombre TEXT NOT NULL,
            apellido TEXT NOT NULL,
            correo TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 2. TABLA: Sesiones
    c.execute('''
        CREATE TABLE IF NOT EXISTS sesiones (
            id TEXT PRIMARY KEY,
            usuario_id TEXT NOT NULL,
            asin TEXT NOT NULL,
            titulo TEXT NOT NULL,
            creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (usuario_id) REFERENCES usuarios (id) ON DELETE CASCADE,
            FOREIGN KEY (asin) REFERENCES productos (asin) ON DELETE CASCADE
        )
    ''')

    # 3. TABLA: Mensajes
    c.execute('''
        CREATE TABLE IF NOT EXISTS mensajes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sesion_id TEXT NOT NULL,
            rol TEXT NOT NULL,
            contenido TEXT NOT NULL,
            creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (sesion_id) REFERENCES sesiones (id) ON DELETE CASCADE
        )
    ''')

    # 4. TABLA: Auditoria
    c.execute('''
        CREATE TABLE IF NOT EXISTS auditoria (
            id TEXT PRIMARY KEY,
            session_id TEXT,
            timestamp TEXT,
            user_prompt TEXT,
            system_response TEXT,
            ttft_ms REAL,
            total_latency_ms REAL,
            tokens_per_second REAL,
            was_blocked BOOLEAN,
            tools_executed TEXT
        )
    ''')

    # 5. TABLA: Productos
    c.execute('''
        CREATE TABLE IF NOT EXISTS productos (
            asin TEXT PRIMARY KEY,
            nombre TEXT NOT NULL,
            caracteristicas_json TEXT
        )
    ''')

    # 6. TABLA: Reseñas (Fuente de la verdad)
    c.execute('''
        CREATE TABLE IF NOT EXISTS resenas (
            review_id TEXT PRIMARY KEY,
            asin TEXT NOT NULL,
            author TEXT,
            rating INTEGER,
            title TEXT,
            body TEXT,
            fecha TEXT,
            verified BOOLEAN,
            FOREIGN KEY (asin) REFERENCES productos (asin) ON DELETE CASCADE
        )
    ''')

    # 7. TABLA: Lista Negra de Tokens JWT (Logout Seguro)
    c.execute('''
        CREATE TABLE IF NOT EXISTS jwt_blacklist (
            token TEXT PRIMARY KEY,
            expiracion TIMESTAMP NOT NULL,
            añadido_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    conn.commit()
    conn.close()
    print("[DB] Esquema relacional SaaS inicializado correctamente.")

if __name__ == "__main__":
    inicializar_base_datos()