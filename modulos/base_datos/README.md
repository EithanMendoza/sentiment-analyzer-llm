# Estructura del Módulo de Base de Datos

Este documento explica la organización de los archivos encargados de manejar la base de datos relacional (SQLite) para el sistema de análisis de reseñas. La estructura sigue el Principio de Responsabilidad Única (SRP) para garantizar que el código sea mantenible, fácil de leer y de escalar.

## 1. Árbol de Directorios

El código se divide en carpetas principales dentro del directorio `modulos/base_datos`, separando las configuraciones, las operaciones directas y las adaptaciones para la Inteligencia Artificial.

```text
AgenteLocalParaResenas/
├── datos/
│   └── base_relacional/
│       └── historial_sesiones.db   # Archivo generado por SQLite (No se sube al repositorio)
│
├── modulos/
│   └── base_datos/
│       ├── conexion.py          
│       ├── tablas_setup.py      
│       │
│       ├── operaciones/         
│       │   ├── usuarios.py          
│       │   ├── sesiones.py          
│       │   └── auditoria.py         
│       │
│       └── adaptadores_ia/      
│           └── formateo_chat.py     
```

## 2. Descripción de Carpetas y Archivos

### 📁 Raíz de `base_datos/` (Configuración e Infraestructura)
Contiene exclusivamente los archivos que establecen las reglas de SQLite y la creación del esquema de tablas. Ningún archivo aquí ejecuta operaciones CRUD (Crear, Leer, Actualizar, Borrar).

| Archivo | Propósito Principal | Responsabilidad |
|---|---|---|
| `conexion.py` | Gestión de la ruta física y conexión a SQLite. | Define la constante `RUTA_DB_RELACIONAL` asegurando que el archivo `.db` se guarde en `datos/base_relacional/`. Contiene la función para abrir la conexión y forzar el uso de llaves foráneas (`PRAGMA foreign_keys = ON`). |
| `tablas_setup.py` | Esquema inicial de la base de datos. | Contiene las instrucciones `CREATE TABLE IF NOT EXISTS` para las tablas `usuarios`, `sesiones`, `mensajes` y `auditoria`. Solo debe ejecutarse al inicializar el proyecto o reconstruir la base de datos. |

### 📁 `operaciones/` (Lógica de Acceso a Datos - CRUD)
Esta carpeta contiene las funciones que operan directamente sobre los registros de las tablas. Se divide por dominio o entidad para evitar archivos monolíticos.

| Archivo | Funciones Clave | Responsabilidad |
|---|---|---|
| `usuarios.py` | `crear_usuario()`, `obtener_usuario_por_correo()` | Manejar el registro, la autenticación y la gestión de la tabla `usuarios`. Retorna tipos de datos básicos de Python (strings, diccionarios). |
| `sesiones.py` | `crear_sesion_si_no_existe()`, `guardar_mensaje()`, `obtener_sesiones_por_usuario()` | Administrar las sesiones de chat y almacenar el historial de mensajes crudos en las tablas `sesiones` y `mensajes`. |
| `auditoria.py` | `guardar_registro_auditoria()` | Registrar métricas de rendimiento del LLM (latencia, tokens, herramientas) en la tabla `auditoria` para monitorización. |

### 📁 `adaptadores_ia/` (Capa de Servicio)
Actúa como puente de comunicación entre la base de datos relacional y el framework de Inteligencia Artificial.

| Archivo | Propósito Principal | Responsabilidad |
|---|---|---|
| `formateo_chat.py` | Traductor de contextos. | Importa funciones de `operaciones/sesiones.py` (para obtener el historial en formato crudo) y los convierte en objetos específicos del framework de IA (ej. `ChatMessage`, `MessageRole` de LlamaIndex). Mantiene la lógica de IA separada de la base de datos. |

## 3. Regla de Ruta para la Base de Datos

Para garantizar que el archivo SQLite (`historial_sesiones.db`) siempre se genere en el directorio correcto y no ensucie la raíz del proyecto, el archivo `conexion.py` utiliza la siguiente ruta absoluta calculada dinámicamente:

```python
import os

# Obtiene la ruta absoluta del directorio raíz del proyecto (subiendo directorios desde modulos/base_datos)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Construye la ruta: /AgenteLocalParaResenas/datos/base_relacional/historial_sesiones.db
RUTA_DB_RELACIONAL = os.path.join(BASE_DIR, "datos", "base_relacional", "historial_sesiones.db")
```

La función encargada de inicializar la base de datos siempre incluye `os.makedirs(os.path.dirname(RUTA_DB_RELACIONAL), exist_ok=True)` para crear las carpetas en caso de que no existan al ejecutar el programa por primera vez.