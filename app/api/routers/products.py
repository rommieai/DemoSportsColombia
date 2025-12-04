"""Endpoints para productos de jugadores - Migrado a Firebase"""
from fastapi import APIRouter, HTTPException, Query, Depends, Body
from typing import List, Optional
from app.schemas.products import (
    ProductResponse, 
    ProductInfo, 
    ProductsListResponse,
    ProductCreateRequest,
    ProductUpdateRequest,
    ProductStatsResponse,
    MigrationResponse
)
from app.services.products_firebase_service import (
    ProductsFirebaseService, 
    get_products_firebase_service
)

router = APIRouter(prefix="/products", tags=["Products"])


# ===== ENDPOINTS DE CONSULTA =====

@router.get("/buscar", response_model=ProductResponse)
async def buscar_producto(
    nombre: str = Query(..., description="Nombre del jugador", min_length=2),
    force_refresh: bool = Query(False, description="Forzar actualización desde Firebase"),
    service: ProductsFirebaseService = Depends(get_products_firebase_service)
):
    """
    Busca un producto por nombre de jugador.
    
    - **nombre**: Nombre del jugador (búsqueda flexible, no case-sensitive)
    - **force_refresh**: Si True, ignora cache y consulta Firebase directamente
    - **Cache**: 1 hora en Firebase
    
    ### Ejemplos:
    - `/products/buscar?nombre=Yáser Asprilla`
    - `/products/buscar?nombre=yaser` (búsqueda parcial)
    - `/products/buscar?nombre=ASPRILLA` (no case-sensitive)
    """
    producto = service.buscar_por_jugador(nombre, force_refresh=force_refresh)
    
    if producto is None:
        # Sugerir jugadores disponibles
        disponibles = service.listar_jugadores()
        return {
            "encontrado": False,
            "producto": None,
            "mensaje": f"Producto para jugador '{nombre}' no encontrado. "
                      f"Jugadores disponibles: {', '.join(disponibles[:5])}"
                      f"{'...' if len(disponibles) > 5 else ''}"
        }
    
    return {
        "encontrado": True,
        "producto": producto,
        "mensaje": None
    }


@router.get("/jugadores", response_model=ProductsListResponse)
async def listar_jugadores(
    force_refresh: bool = Query(False, description="Forzar actualización desde Firebase"),
    service: ProductsFirebaseService = Depends(get_products_firebase_service)
):
    """
    Obtiene la lista de nombres de todos los jugadores con productos.
    
    - **force_refresh**: Si True, ignora cache
    - **Cache**: 30 minutos en Firebase
    - **Útil para**: Autocomplete, dropdowns, validación
    """
    jugadores = service.listar_jugadores(force_refresh=force_refresh)
    
    return {
        "total": len(jugadores),
        "jugadores": jugadores
    }


@router.get("/todos", response_model=List[ProductInfo])
async def obtener_todos_productos(
    force_refresh: bool = Query(False, description="Forzar actualización desde Firebase"),
    service: ProductsFirebaseService = Depends(get_products_firebase_service)
):
    """
    Obtiene información completa de todos los productos.
    
    - **force_refresh**: Si True, ignora cache
    - **Cache**: 30 minutos en Firebase
    - **Útil para**: Cargar catálogo completo, exportar datos
    """
    return service.obtener_todos(force_refresh=force_refresh)


@router.get("/{nombre}", response_model=ProductResponse)
async def obtener_producto(
    nombre: str,
    force_refresh: bool = Query(False, description="Forzar actualización desde Firebase"),
    service: ProductsFirebaseService = Depends(get_products_firebase_service)
):
    """
    Obtiene información de un producto por nombre de jugador (path parameter).
    
    - **nombre**: Nombre del jugador en la URL
    - **force_refresh**: Si True, ignora cache
    
    ### Ejemplo:
    - `/products/Yáser%20Asprilla`
    """
    producto = service.buscar_por_jugador(nombre, force_refresh=force_refresh)
    
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


# ===== ENDPOINTS DE ADMINISTRACIÓN (NUEVO) =====

@router.post("/crear", response_model=dict)
async def crear_producto(
    producto: ProductCreateRequest = Body(...),
    service: ProductsFirebaseService = Depends(get_products_firebase_service)
):
    """
    Crea un nuevo producto en Firebase.
    
    **Requiere autenticación** (implementar según necesidad)
    
    Args:
        producto: Información completa del producto
            - Jugador (str): Nombre del jugador
            - Foto (str): URL de la foto
            - Link_Producto (str): URL del producto
            - Precio (str): Precio del producto
    
    Returns:
        Confirmación de creación
    """
    try:
        success = service.crear_producto(producto.dict())
        
        if not success:
            raise HTTPException(500, "Error al crear el producto en Firebase")
        
        return {
            "mensaje": f"Producto para '{producto.Jugador}' creado exitosamente",
            "jugador": producto.Jugador
        }
    
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Error creando producto: {str(e)}")


@router.put("/actualizar/{nombre_jugador}", response_model=dict)
async def actualizar_producto(
    nombre_jugador: str,
    actualizacion: ProductUpdateRequest = Body(...),
    service: ProductsFirebaseService = Depends(get_products_firebase_service)
):
    """
    Actualiza un producto existente.
    
    **Requiere autenticación** (implementar según necesidad)
    
    Args:
        nombre_jugador: Nombre del jugador cuyo producto se actualizará
        actualizacion: Campos a actualizar (todos opcionales)
    
    Returns:
        Confirmación de actualización
    """
    # Filtrar solo campos presentes
    datos_actualizar = {
        k: v for k, v in actualizacion.dict().items() 
        if v is not None
    }
    
    if not datos_actualizar:
        raise HTTPException(400, "No se proporcionaron campos para actualizar")
    
    success = service.actualizar_producto(nombre_jugador, datos_actualizar)
    
    if not success:
        raise HTTPException(404, f"Producto para '{nombre_jugador}' no encontrado")
    
    return {
        "mensaje": f"Producto de '{nombre_jugador}' actualizado exitosamente",
        "campos_actualizados": list(datos_actualizar.keys())
    }


@router.delete("/eliminar/{nombre_jugador}", response_model=dict)
async def eliminar_producto(
    nombre_jugador: str,
    service: ProductsFirebaseService = Depends(get_products_firebase_service)
):
    """
    Elimina un producto de Firebase.
    
    **Requiere autenticación** (implementar según necesidad)
    
    Args:
        nombre_jugador: Nombre del jugador cuyo producto se eliminará
    
    Returns:
        Confirmación de eliminación
    """
    success = service.eliminar_producto(nombre_jugador)
    
    if not success:
        raise HTTPException(404, f"Producto para '{nombre_jugador}' no encontrado")
    
    return {
        "mensaje": f"Producto de '{nombre_jugador}' eliminado exitosamente",
        "jugador": nombre_jugador
    }


# ===== ENDPOINTS DE UTILIDAD =====

@router.get("/admin/stats", response_model=ProductStatsResponse)
async def obtener_estadisticas(
    service: ProductsFirebaseService = Depends(get_products_firebase_service)
):
    """
    Obtiene estadísticas sobre los productos en Firebase.
    
    - Total de productos
    - Lista de jugadores
    - Última actualización
    """
    return service.get_stats()


@router.get("/admin/health", response_model=dict)
async def verificar_salud(
    service: ProductsFirebaseService = Depends(get_products_firebase_service)
):
    """
    Verifica que el servicio de productos esté funcionando correctamente.
    
    - Verifica conexión a Firebase
    - Verifica disponibilidad de datos
    """
    return service.health_check()


@router.post("/admin/migrate-from-json", response_model=MigrationResponse)
async def migrar_desde_json(
    custom_path: Optional[str] = Query(
        None, 
        description="Ruta personalizada al archivo JSON (opcional)"
    ),
    service: ProductsFirebaseService = Depends(get_products_firebase_service)
):
    """
    Migra datos desde el archivo JSON local a Firebase.
    
    **IMPORTANTE**: Este endpoint debe ejecutarse UNA VEZ para migrar datos existentes.
    
    **Requiere autenticación de administrador**
    
    Args:
        custom_path: Ruta opcional al archivo JSON. 
                    Si no se proporciona, busca en:
                    - /home/DemoSportsColombia/DemoSportsColombia/data/jugadores.json
                    - ./data/jugadores.json
                    - (ruta del proyecto)/data/jugadores.json
    
    Returns:
        Estadísticas de la migración (exitosos, errores, total)
        
    Ejemplos:
        - POST /products/admin/migrate-from-json
        - POST /products/admin/migrate-from-json?custom_path=/ruta/al/archivo.json
    """
    try:
        stats = service.migrate_from_json(custom_path=custom_path)
        return stats
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, f"Error en migración: {str(e)}")


@router.post("/admin/invalidate-cache", response_model=dict)
async def invalidar_cache(
    service: ProductsFirebaseService = Depends(get_products_firebase_service)
):
    """
    Invalida todos los caches de productos en Firebase.
    
    **Útil cuando**: Se necesita forzar recarga de datos
    """
    service._invalidate_all_cache()
    
    return {
        "mensaje": "Cache de productos invalidado exitosamente",
        "accion": "Los próximos requests consultarán Firebase directamente"
    }