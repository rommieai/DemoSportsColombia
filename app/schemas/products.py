"""Esquemas Pydantic para productos de jugadores"""
from typing import Optional, List
from pydantic import BaseModel, Field

class ProductInfo(BaseModel):
    """Información de un producto asociado a un jugador"""
    Jugador: str = Field(..., description="Nombre del jugador")
    Producto: str = Field(..., description="Nombre del producto asociado")
    Foto: str = Field(..., description="Nombre del archivo de foto")
    Link: str = Field(..., description="URL del producto en Adidas")
    Foto_Link: str = Field(..., description="URL de Google Drive con la foto")

    class Config:
        json_schema_extra = {
            "example": {
                "Jugador": "Yáser Asprilla",
                "Producto": "Minibalón de local Colombia de la FCF Mundial 2026",
                "Foto": "MINIBALON_DE_LOCAL_COLOMBIAN_DE_LA_FCF_DE_LA_COPA_MUNDIAL_2026_Amarillo_KH0298_01_00_standard.avif",
                "Link": "https://www.adidas.co/minibalon-de-local-colombian-de-la-fcf-de-la-copa-mundial-2026/KH0298.html",
                "Foto_Link": "https://drive.google.com/file/d/1vlPm2bMKmiTQGU6kriG6gYjlE2EhrflX/view?usp=drive_link"
            }
        }

class ProductResponse(BaseModel):
    """Respuesta con información del producto"""
    encontrado: bool
    producto: Optional[ProductInfo] = None
    mensaje: Optional[str] = None

class ProductsListResponse(BaseModel):
    """Respuesta con lista de todos los productos/jugadores"""
    total: int
    jugadores: List[str]  # Mantenemos "jugadores" porque es la lista de nombres