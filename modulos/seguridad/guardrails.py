# modulos/seguridad/guardrails.py

# Lista negra de heurísticas comunes de inyección de prompts
PATRONES_PROHIBIDOS = [
    "ignora las instrucciones",
    "ignora tus instrucciones",
    "olvida las instrucciones",
    "revela tu system prompt",
    "cuál es tu system prompt",
    "eres un desarrollador",  # Intento de cambio de rol
    "asume el rol de",
    "bypass",
    "sudo",
    "system: "
]

def validar_prompt_seguro(prompt_usuario: str) -> tuple[bool, str]:
    """
    Analiza el texto del usuario buscando intentos de inyección.
    Retorna (Es_Seguro, Mensaje_De_Bloqueo).
    """
    prompt_limpio = prompt_usuario.lower().strip()
    
    for patron in PATRONES_PROHIBIDOS:
        if patron in prompt_limpio:
            # Si detectamos una amenaza, devolvemos False y un mensaje genérico
            return False, "La solicitud contiene patrones no permitidos y ha sido bloqueada."
            
    # Validación de longitud (para evitar ataques de denegación de servicio / saturación de RAM)
    if len(prompt_limpio) > 1000:
        return False, "El texto excede la longitud máxima permitida (1000 caracteres)."

    return True, "OK"