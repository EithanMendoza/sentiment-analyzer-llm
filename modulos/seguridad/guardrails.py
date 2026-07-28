"""
Guardrails de seguridad para sanitizar la entrada del usuario.
Previene inyecciones de prompt (Prompt Injections) y ataques de denegación de servicio (DoS).
"""

import re
import unicodedata

# 1. Lista expandida y compilada en Regex para detectar patrones maliciosos de manera flexible
# Detecta variaciones con espacios múltiples, caracteres intermedios y variaciones comunes de evasión.
PATRONES_PROHIBIDOS = [
    r"ignora\s+(?:las\s+)?instrucciones",
    r"olvida\s+(?:las\s+)?instrucciones",
    r"revela\s+(?:tu\s+)?system\s*prompt",
    r"cual\s+es\s+tu\s+system\s*prompt",
    r"eres\s+un\s+desarrollador",
    r"asume\s+(?:el\s+)?rol\s+de",
    r"\bbypass\b",
    r"\bsudo\b",
    r"\bsystem\s*:",
    r"danos\s+instrucciones\s+previas",
    r"actua\s+como",
    r"mode\s+developer",
    r"jailbreak"
]

# Compilamos las expresiones regulares con la bandera IGNORECASE para optimizar la velocidad de ejecución
REGEX_PROHIBIDOS = [re.compile(patron, re.IGNORECASE) for patron in PATRONES_PROHIBIDOS]


def normalizar_texto(texto: str) -> str:
    """
    Normaliza el texto del usuario: elimina acentos/diacríticos y estandariza espacios
    para evitar evasiones basadas en codificación (Unicode Evasion).
    """
    # Convierte caracteres combinados a su forma descompuesta (Ej: 'ó' -> 'o' + '´')
    texto_descompuesto = unicodedata.normalize('NFD', texto)
    # Filtra los caracteres que son diacríticos/acentos
    texto_sin_acentos = "".join([c for c in texto_descompuesto if unicodedata.category(c) != 'Mn'])
    # Reemplaza múltiples espacios, tabulaciones o saltos de línea por un solo espacio
    return re.sub(r'\s+', ' ', texto_sin_acentos).strip()


def validar_prompt_seguro(prompt_usuario: str) -> tuple[bool, str]:
    """
    Analiza el texto del usuario buscando intentos de inyección y ataques DoS.
    Retorna (Es_Seguro, Mensaje_De_Bloqueo).
    """
    if not prompt_usuario:
        return True, "OK"

    # 1. Validación estricta de longitud previa a cualquier procesamiento pesado (Protección DoS de RAM)
    if len(prompt_usuario) > 1000:
        return False, "La solicitud excede la longitud máxima permitida."

    # 2. Normalización de texto para derribar variantes como "Ígnórá lÁS ínstrúccíónés"
    prompt_limpio = normalizar_texto(prompt_usuario)

    # 3. Escaneo mediante Expresiones Regulares
    for regex in REGEX_PROHIBIDOS:
        if regex.search(prompt_limpio):
            # Retornamos un mensaje genérico y limpio de producción sin etiquetas internas
            return False, "La solicitud contiene términos o estructuras no permitidos."

    return True, "OK"