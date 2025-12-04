"""Servicio de productos con Firebase - Reemplaza lectura de JSON estático"""
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from app.services.firebase_service import firebase_service
import json
from pathlib import Path


class ProductsFirebaseService:
    """Servicio para productos de jugadores usando Firebase como fuente de datos"""
    
    # Colecciones de Firebase
    COLLECTION_PRODUCTS = "player_products"
    COLLECTION_METADATA = "products_metadata"
    
    # TTL para cache
    TTL_PRODUCTS = 3600  # 1 hora (datos semi-estáticos)
    TTL_ALL_PRODUCTS = 1800  # 30 minutos para lista completa
    
    def __init__(self, json_path: Optional[str] = None):
        """
        Args:
            json_path: Ruta al JSON (solo se usa para migración inicial)
                      Si es None, usa la ruta por defecto relativa al proyecto
        """
        if json_path is None:
            # Obtener ruta absoluta del proyecto
            project_root = Path(__file__).parent.parent.parent
            json_path = project_root / "data" / "jugadores.json"
        
        self.json_path = Path(json_path)
        self.fb = firebase_service
    
    # ===== BÚSQUEDA Y CONSULTA =====
    
    def buscar_por_jugador(
        self, 
        nombre: str, 
        force_refresh: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        Busca un producto por nombre de jugador
        
        Args:
            nombre: Nombre del jugador (búsqueda case-insensitive)
            force_refresh: Si True, fuerza actualización desde Firebase
        
        Returns:
            Información del producto o None si no se encuentra
        """
        nombre_normalized = self._normalize_name(nombre)
        doc_id = f"player_{nombre_normalized}"
        
        # 1. Intentar obtener de cache de Firebase
        if not force_refresh:
            cached_data = self.fb.get_if_valid(self.COLLECTION_PRODUCTS, doc_id)
            if cached_data:
                print(f"✓ Producto de '{nombre}' obtenido de Firebase cache")
                return cached_data
        
        # 2. Si no está en cache, buscar en todos los productos
        all_products = self._get_all_products_from_firebase()
        
        if not all_products:
            return None
        
        # 3. Búsqueda flexible
        result = self._search_in_products(nombre, all_products)
        
        # 4. Guardar resultado en cache individual
        if result:
            self.fb.set_with_ttl(
                self.COLLECTION_PRODUCTS, 
                doc_id, 
                result, 
                self.TTL_PRODUCTS
            )
        
        return result
    
    def listar_jugadores(self, force_refresh: bool = False) -> List[str]:
        """
        Retorna lista de nombres de todos los jugadores
        
        Args:
            force_refresh: Si True, fuerza actualización desde Firebase
        """
        doc_id = "all_players_list"
        
        # Intentar obtener lista de cache
        if not force_refresh:
            cached_list = self.fb.get_if_valid(self.COLLECTION_METADATA, doc_id)
            if cached_list:
                print(f"✓ Lista de jugadores obtenida de Firebase cache")
                return cached_list
        
        # Obtener todos los productos y extraer nombres
        all_products = self._get_all_products_from_firebase()
        jugadores = [p["Jugador"] for p in all_products]
        
        # Guardar en cache
        self.fb.set_with_ttl(
            self.COLLECTION_METADATA, 
            doc_id, 
            jugadores, 
            self.TTL_ALL_PRODUCTS
        )
        
        return jugadores
    
    def obtener_todos(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """
        Retorna todos los productos con información completa
        
        Args:
            force_refresh: Si True, fuerza actualización desde Firebase
        """
        return self._get_all_products_from_firebase(force_refresh)
    
    # ===== ADMINISTRACIÓN (NUEVO) =====
    
    def crear_producto(self, producto: Dict[str, Any]) -> bool:
        """
        Crea un nuevo producto en Firebase
        
        Args:
            producto: Diccionario con información del producto
                Debe incluir: Jugador, Foto, Link_Producto, Precio
        
        Returns:
            True si se creó exitosamente
        """
        if not self._validate_product(producto):
            raise ValueError("Producto inválido: faltan campos requeridos")
        
        nombre_normalized = self._normalize_name(producto["Jugador"])
        doc_id = f"player_{nombre_normalized}"
        
        # Agregar metadata
        producto["created_at"] = datetime.now(timezone.utc).isoformat()
        producto["updated_at"] = datetime.now(timezone.utc).isoformat()
        
        # Guardar en Firebase
        success = self.fb.set_with_ttl(
            self.COLLECTION_PRODUCTS, 
            doc_id, 
            producto, 
            self.TTL_PRODUCTS
        )
        
        if success:
            # Invalidar cache de lista completa
            self._invalidate_all_cache()
        
        return success
    
    def actualizar_producto(
        self, 
        nombre_jugador: str, 
        nuevos_datos: Dict[str, Any]
    ) -> bool:
        """
        Actualiza un producto existente
        
        Args:
            nombre_jugador: Nombre del jugador
            nuevos_datos: Campos a actualizar
        
        Returns:
            True si se actualizó exitosamente
        """
        nombre_normalized = self._normalize_name(nombre_jugador)
        doc_id = f"player_{nombre_normalized}"
        
        # Obtener producto actual
        producto_actual = self.fb.get_if_valid(self.COLLECTION_PRODUCTS, doc_id)
        
        if not producto_actual:
            return False
        
        # Actualizar campos
        producto_actualizado = {**producto_actual, **nuevos_datos}
        producto_actualizado["updated_at"] = datetime.now(timezone.utc).isoformat()
        
        # Guardar
        success = self.fb.set_with_ttl(
            self.COLLECTION_PRODUCTS, 
            doc_id, 
            producto_actualizado, 
            self.TTL_PRODUCTS
        )
        
        if success:
            self._invalidate_all_cache()
        
        return success
    
    def eliminar_producto(self, nombre_jugador: str) -> bool:
        """
        Elimina un producto
        
        Args:
            nombre_jugador: Nombre del jugador
        
        Returns:
            True si se eliminó exitosamente
        """
        nombre_normalized = self._normalize_name(nombre_jugador)
        doc_id = f"player_{nombre_normalized}"
        
        success = self.fb.delete(self.COLLECTION_PRODUCTS, doc_id)
        
        if success:
            self._invalidate_all_cache()
        
        return success
    
    # ===== MIGRACIÓN DESDE JSON =====
    
    def migrate_from_json(self, custom_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Migra datos desde el archivo JSON a Firebase
        
        Args:
            custom_path: Ruta personalizada al JSON (opcional)
        
        NOTA: Esta función debe ejecutarse UNA VEZ para migrar datos existentes
        
        Returns:
            Estadísticas de la migración
        """
        # Usar ruta personalizada si se proporciona
        json_path = Path(custom_path) if custom_path else self.json_path
        
        # Verificar que el archivo existe
        if not json_path.exists():
            # Intentar rutas alternativas comunes
            alternative_paths = [
                Path("/home/DemoSportsColombia/DemoSportsColombia/data/jugadores.json"),
                Path.cwd() / "data" / "jugadores.json",
                Path(__file__).parent.parent.parent / "data" / "jugadores.json"
            ]
            
            for alt_path in alternative_paths:
                if alt_path.exists():
                    json_path = alt_path
                    print(f"✓ Archivo encontrado en: {json_path}")
                    break
            else:
                # Ninguna ruta funcionó
                raise FileNotFoundError(
                    f"No se encontró el archivo jugadores.json en ninguna de estas rutas:\n"
                    f"  - {json_path}\n" + 
                    "\n".join(f"  - {p}" for p in alternative_paths)
                )
        
        print(f"📂 Leyendo archivo: {json_path}")
        
        # Leer JSON
        with open(json_path, 'r', encoding='utf-8') as f:
            productos_json = json.load(f)
        
        print(f"📦 Migrando {len(productos_json)} productos a Firebase...")
        
        exitosos = 0
        errores = 0
        errores_detalle = []
        
        for producto_json in productos_json:
            try:
                # Normalizar producto desde formato JSON a formato schema
                producto_normalizado = self._normalize_product_from_json(producto_json)
                
                if self.crear_producto(producto_normalizado):
                    exitosos += 1
                    print(f"  ✓ {producto_normalizado.get('Jugador')}")
                else:
                    errores += 1
                    errores_detalle.append(f"{producto_normalizado.get('Jugador')}: Error al guardar")
            except Exception as e:
                print(f"  ❌ Error migrando {producto_json.get('Jugador')}: {str(e)}")
                errores += 1
                errores_detalle.append(f"{producto_json.get('Jugador')}: {str(e)}")
        
        stats = {
            "total": len(productos_json),
            "exitosos": exitosos,
            "errores": errores,
            "errores_detalle": errores_detalle,
            "archivo_fuente": str(json_path),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        # Guardar estadísticas de migración
        self.fb.set_with_ttl(
            self.COLLECTION_METADATA,
            "migration_stats",
            stats,
            86400  # 24 horas
        )
        
        print(f"✅ Migración completada: {exitosos} exitosos, {errores} errores")
        
        return stats
    
    # ===== MÉTODOS PRIVADOS =====
    
    def _get_all_products_from_firebase(
        self, 
        force_refresh: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Obtiene todos los productos desde Firebase
        
        OPTIMIZACIÓN: Usa un documento maestro con todos los productos
        en lugar de consultar cada documento individual
        """
        doc_id = "all_products_master"
        
        if not force_refresh:
            cached_data = self.fb.get_if_valid(self.COLLECTION_METADATA, doc_id)
            if cached_data:
                print(f"✓ Todos los productos obtenidos de Firebase cache")
                return cached_data
        
        # Obtener todos los documentos de la colección
        print(f"⚡ Consultando todos los productos desde Firebase...")
        all_docs = self.fb.get_all_valid(self.COLLECTION_PRODUCTS)
        
        # Extraer solo los datos (sin metadata de Firebase)
        products = [doc["data"] for doc in all_docs if doc.get("data")]
        
        # Guardar en cache maestro
        self.fb.set_with_ttl(
            self.COLLECTION_METADATA,
            doc_id,
            products,
            self.TTL_ALL_PRODUCTS
        )
        
        return products
    
    def _search_in_products(
        self, 
        nombre: str, 
        products: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """
        Busca un jugador en la lista de productos (búsqueda flexible)
        """
        nombre_lower = nombre.lower().strip()
        
        # 1. Búsqueda exacta
        for item in products:
            if item["Jugador"].lower() == nombre_lower:
                return item
        
        # 2. Búsqueda parcial
        for item in products:
            if nombre_lower in item["Jugador"].lower():
                return item
        
        return None
    
    def _normalize_name(self, nombre: str) -> str:
        """Normaliza un nombre para usar como doc_id"""
        return nombre.lower().strip().replace(" ", "_")
    
    def _validate_product(self, producto: Dict[str, Any]) -> bool:
        """Valida que un producto tenga los campos requeridos"""
        # Campos requeridos en el schema
        required_fields = ["Jugador", "Foto", "Link_Producto"]
        return all(field in producto for field in required_fields)
    
    def _normalize_product_from_json(self, producto_json: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normaliza un producto desde el formato del JSON al formato del schema
        
        JSON tiene: Jugador, Producto, Foto, Link, Foto_Link
        Schema espera: Jugador, Foto, Link_Producto, Precio (opcional)
        """
        return {
            "Jugador": producto_json.get("Jugador"),
            "Producto": producto_json.get("Producto", ""),  # Descripción del producto
            "Foto": producto_json.get("Foto", ""),  # Nombre del archivo
            "Foto_Link": producto_json.get("Foto_Link", ""),  # URL de Google Drive
            "Link_Producto": producto_json.get("Link", ""),  # Link de Adidas
            "Precio": producto_json.get("Precio", "Precio no disponible")
        }
    
    def _invalidate_all_cache(self) -> None:
        """Invalida todos los caches relacionados con productos"""
        self.fb.delete(self.COLLECTION_METADATA, "all_products_master")
        self.fb.delete(self.COLLECTION_METADATA, "all_players_list")
    
    # ===== UTILIDADES =====
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Obtiene estadísticas sobre los productos en Firebase
        """
        all_products = self._get_all_products_from_firebase()
        
        return {
            "total_productos": len(all_products),
            "jugadores": [p["Jugador"] for p in all_products],
            "ultima_actualizacion": datetime.now(timezone.utc).isoformat()
        }
    
    def health_check(self) -> Dict[str, Any]:
        """
        Verifica que el servicio esté funcionando correctamente
        """
        try:
            all_products = self._get_all_products_from_firebase()
            return {
                "status": "healthy",
                "productos_disponibles": len(all_products),
                "firebase_conectado": True
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "firebase_conectado": False
            }


# ===== DEPENDENCY INJECTION =====

_products_service_instance = None

def get_products_firebase_service() -> ProductsFirebaseService:
    """Dependency para obtener el servicio de productos con Firebase"""
    global _products_service_instance
    if _products_service_instance is None:
        _products_service_instance = ProductsFirebaseService()
    return _products_service_instance