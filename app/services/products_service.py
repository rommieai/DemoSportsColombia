"""Servicio para manejar información de productos de jugadores"""
import json
from pathlib import Path
from typing import Optional, List, Dict, Any
from functools import lru_cache

class ProductsService:
    """Servicio para buscar productos asociados a jugadores"""
    
    def __init__(self, json_path: str = "data/jugadores.json"):
        self.json_path = Path(json_path)
        self._data: Optional[List[Dict[str, Any]]] = None
    
    def _load_data(self) -> List[Dict[str, Any]]:
        """Carga los datos del JSON (con caché)"""
        if self._data is None:
            if not self.json_path.exists():
                raise FileNotFoundError(f"No se encontró el archivo {self.json_path}")
            
            with open(self.json_path, 'r', encoding='utf-8') as f:
                self._data = json.load(f)
        
        return self._data
    
    def buscar_por_jugador(self, nombre: str) -> Optional[Dict[str, Any]]:
        """
        Busca un producto por nombre de jugador (búsqueda flexible)
        
        Args:
            nombre: Nombre del jugador (búsqueda case-insensitive y parcial)
        
        Returns:
            Información del producto o None si no se encuentra
        """
        data = self._load_data()
        nombre_lower = nombre.lower().strip()
        
        # Búsqueda exacta primero
        for item in data:
            if item["Jugador"].lower() == nombre_lower:
                return item
        
        # Búsqueda parcial si no hay coincidencia exacta
        for item in data:
            if nombre_lower in item["Jugador"].lower():
                return item
        
        return None
    
    def listar_jugadores(self) -> List[str]:
        """
        Retorna lista de nombres de todos los jugadores con productos
        """
        data = self._load_data()
        return [item["Jugador"] for item in data]
    
    def obtener_todos(self) -> List[Dict[str, Any]]:
        """
        Retorna todos los productos con su información completa
        """
        return self._load_data()
    
    def reload_data(self) -> None:
        """
        Recarga los datos del JSON (útil si el archivo se actualiza)
        """
        self._data = None

@lru_cache()
def get_products_service() -> ProductsService:
    """Dependency para obtener el servicio de productos"""
    return ProductsService()