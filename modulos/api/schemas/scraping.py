from pydantic import BaseModel, field_validator
from urllib.parse import urlparse, urlunparse

class SolicitudScraping(BaseModel):
    url_o_asin: str
    marketplace: str = "com.mx"

    @field_validator('url_o_asin')
    @classmethod
    def sanitizar_url_ssrf(cls, value: str) -> str:
        """
        Interviene la URL de entrada para eliminar queries y fragmentos
        que puedan ser utilizados para ataques SSRF u ofuscar la ruta.
        Si la entrada es un ASIN puro (no es una URL), la deja pasar intacta.
        """
        value = value.strip()
        
        # Si parece una URL (contiene esquema web o el dominio base)
        if "http://" in value or "https://" in value or "amazon." in value:
            # Aseguramos que tenga esquema para que urlparse no se confunda
            if not value.startswith(("http://", "https://")):
                value = f"https://{value}"
                
            parsed = urlparse(value)
            
            # Reconstruimos la URL dejando los campos de query (index 4) y fragmento (index 5) completamente vacíos.
            # urlunparse recibe: (scheme, netloc, path, params, query, fragment)
            url_limpia = urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, "", ""))
            
            return url_limpia
            
        # Si no parece una URL (ej. es un ASIN directo de 10 caracteres), la devolvemos sin alterar
        return value