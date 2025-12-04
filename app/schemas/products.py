"""Esquemas Pydantic para productos de jugadores"""
from typing import Optional, List
from pydantic import BaseModel, Field, HttpUrl


# ===== MODELOS DE DATOS =====

class ProductInfo(BaseModel):
    """Información completa de un producto"""
    Jugador: str = Field(..., description="Nombre del jugador")
    Producto: Optional[str] = Field(None, description="Descripción del producto")
    Foto: str = Field(..., description="Nombre del archivo de foto")
    Foto_Link: Optional[str] = Field(None, description="URL de la foto en Google Drive")
    Link_Producto: str = Field(..., description="URL del producto en tienda Adidas")
    Precio: Optional[str] = Field("Precio no disponible", description="Precio del producto")
    created_at: Optional[str] = Field(None, description="Fecha de creación (ISO)")
    updated_at: Optional[str] = Field(None, description="Última actualización (ISO)")


class ProductResponse(BaseModel):
    """Respuesta al buscar un producto"""
    encontrado: bool
    producto: Optional[ProductInfo]
    mensaje: Optional[str]


class ProductsListResponse(BaseModel):
    """Respuesta con lista de jugadores"""
    total: int
    jugadores: List[str]


# ===== MODELOS PARA ADMINISTRACIÓN (NUEVO) =====

class ProductCreateRequest(BaseModel):
    """Request para crear un nuevo producto"""
    Jugador: str = Field(..., min_length=2, description="Nombre del jugador")
    Producto: Optional[str] = Field(None, description="Descripción del producto")
    Foto: str = Field(..., description="Nombre del archivo de foto")
    Foto_Link: Optional[str] = Field(None, description="URL de la foto en Google Drive")
    Link_Producto: str = Field(..., description="URL del producto en tienda Adidas")
    Precio: Optional[str] = Field("Precio no disponible", description="Precio del producto")
    
    class Config:
        json_schema_extra = {
            "example": {
                "Jugador": "Yáser Asprilla",
                "Producto": "Minibalón de local Colombia de la FCF Mundial 2026",
                "Foto": "MINIBALON_DE_LOCAL_COLOMBIAN_DE_LA_FCF_DE_LA_COPA_MUNDIAL_2026_Amarillo_KH0298_01_00_standard.avif",
                "Foto_Link": "https://drive.google.com/file/d/1vlPm2bMKmiTQGU6kriG6gYjlE2EhrflX/view?usp=drive_link",
                "Link_Producto": "https://www.adidas.co/minibalon-de-local-colombian-de-la-fcf-de-la-copa-mundial-2026/KH0298.html",
                "Precio": "$99.99"
            }
        }


class ProductUpdateRequest(BaseModel):
    """Request para actualizar un producto existente (todos los campos opcionales)"""
    Jugador: Optional[str] = Field(None, description="Nuevo nombre del jugador")
    Producto: Optional[str] = Field(None, description="Nueva descripción del producto")
    Foto: Optional[str] = Field(None, description="Nuevo nombre de archivo de foto")
    Foto_Link: Optional[str] = Field(None, description="Nueva URL de foto en Google Drive")
    Link_Producto: Optional[str] = Field(None, description="Nueva URL del producto")
    Precio: Optional[str] = Field(None, description="Nuevo precio")
    
    class Config:
        json_schema_extra = {
            "example": {
                "Foto_Link": "https://drive.google.com/file/d/nueva-foto-id",
                "Precio": "$89.99"
            }
        }


class ProductStatsResponse(BaseModel):
    """Respuesta con estadísticas de productos"""
    total_productos: int
    jugadores: List[str]
    ultima_actualizacion: str


class MigrationResponse(BaseModel):
    """Respuesta de migración desde JSON"""
    total: int
    exitosos: int
    errores: int
    errores_detalle: List[str] = []
    archivo_fuente: str
    timestamp: str