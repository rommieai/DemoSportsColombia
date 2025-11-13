"""Endpoints para productos de jugadores"""
from fastapi import APIRouter, HTTPException, Query, Depends
from typing import List
from app.schemas.products import (
    ProductResponse, 
    ProductInfo, 
    ProductsListResponse
)
from app.services.products_service import ProductsService, get_products_service

router = APIRouter(prefix="/products", tags=["Products"])

@router.get("/buscar", response_model=ProductResponse)
async def buscar_producto(
    nombre: str = Query(..., description="Nombre del jugador para buscar su producto", min_length=2),
    service: ProductsService = Depends(get_products_service)
):
    """
    Busca un producto por nombre de jugador y retorna su información.
    
    - **nombre**: Nombre del jugador (búsqueda flexible, no case-sensitive)
    - **Retorna**: Información del producto incluyendo foto y links
    
    ### Ejemplos:
    - `/products/buscar?nombre=Yáser Asprilla`
    - `/products/buscar?nombre=yaser` (búsqueda parcial)
    - `/products/buscar?nombre=ASPRILLA` (no case-sensitive)
    """
    producto = service.buscar_por_jugador(nombre)
    
    if producto is None:
        # Sugerir jugadores disponibles
        disponibles = service.listar_jugadores()
        return {
            "encontrado": False,
            "producto": None,
            "mensaje": f"Producto para jugador '{nombre}' no encontrado. Jugadores disponibles: {', '.join(disponibles[:5])}{'...' if len(disponibles) > 5 else ''}"
        }
    
    return {
        "encontrado": True,
        "producto": producto,
        "mensaje": None
    }

@router.get("/jugadores", response_model=ProductsListResponse)
async def listar_jugadores(
    service: ProductsService = Depends(get_products_service)
):
    """
    Obtiene la lista de nombres de todos los jugadores con productos disponibles.
    
    - **Retorna**: Lista con los nombres de todos los jugadores
    - **Útil para**: Autocomplete, dropdowns, validación
    """
    jugadores = service.listar_jugadores()
    
    return {
        "total": len(jugadores),
        "jugadores": jugadores
    }

@router.get("/todos", response_model=List[ProductInfo])
async def obtener_todos_productos(
    service: ProductsService = Depends(get_products_service)
):
    """
    Obtiene información completa de todos los productos.
    
    - **Retorna**: Lista completa con toda la información de cada producto
    - **Útil para**: Cargar catálogo completo, exportar datos
    """
    return service.obtener_todos()

@router.get("/{nombre}", response_model=ProductResponse)
async def obtener_producto(
    nombre: str,
    service: ProductsService = Depends(get_products_service)
):
    """
    Obtiene información de un producto por nombre de jugador (path parameter).
    
    - **nombre**: Nombre del jugador en la URL
    
    ### Ejemplo:
    - `/products/Yáser%20Asprilla`
    """
    producto = service.buscar_por_jugador(nombre)
    
    if producto is None:
        raise HTTPException(
            status_code=404, 
            detail=f"Producto para jugador '{nombre}' no encontrado"
        )
    
    return {
        "encontrado": True,
        "producto": producto,
        "mensaje": None
    }

@router.post("/reload")
async def reload_data(
    service: ProductsService = Depends(get_products_service)
):
    """
    Recarga los datos del archivo JSON.
    
    - **Útil cuando**: Se actualiza el archivo jugadores.json sin reiniciar el servidor
    """
    service.reload_data()
    total = len(service.listar_jugadores())
    
    return {
        "mensaje": "Datos recargados exitosamente",
        "total_productos": total
    }