from pydantic import BaseModel

class SolicitudScraping(BaseModel):
    url_o_asin: str
    marketplace: str = "com.mx"