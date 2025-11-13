"""Sistema de caché para la API de fútbol"""
import time
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

class CacheManager:
    """Gestor de caché simple con TTL"""
    
    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._last_events: Dict[int, list] = {}
        self._stats_cache: Dict[int, Dict[str, Any]] = {}
    
    def get(self, key: str, ttl: int = 300) -> Optional[Any]:
        """Obtiene un valor del caché si no ha expirado"""
        if key not in self._cache:
            return None
        
        entry = self._cache[key]
        if time.time() - entry["timestamp"] > ttl:
            del self._cache[key]
            return None
        
        return entry["data"]
    
    def set(self, key: str, value: Any) -> None:
        """Almacena un valor en el caché"""
        self._cache[key] = {
            "data": value,
            "timestamp": time.time()
        }
    
    def get_last_events(self, fixture_id: int) -> list:
        """Obtiene los últimos eventos de un partido"""
        return self._last_events.get(fixture_id, [])
    
    def set_last_events(self, fixture_id: int, events: list) -> None:
        """Almacena los últimos eventos de un partido"""
        # Limita a 300 eventos por partido
        if len(events) > 300:
            events = events[-300:]
        self._last_events[fixture_id] = events
    
    def get_stats(self, fixture_id: int, ttl: int = 60) -> Optional[Any]:
        """Obtiene estadísticas cacheadas de un partido"""
        if fixture_id not in self._stats_cache:
            return None
        
        entry = self._stats_cache[fixture_id]
        if time.time() - entry["timestamp"] > ttl:
            del self._stats_cache[fixture_id]
            return None
        
        return entry["data"]
    
    def set_stats(self, fixture_id: int, stats: Any) -> None:
        """Almacena estadísticas de un partido"""
        self._stats_cache[fixture_id] = {
            "data": stats,
            "timestamp": time.time()
        }
    
    def clear(self) -> None:
        """Limpia todo el caché"""
        self._cache.clear()
        self._last_events.clear()
        self._stats_cache.clear()

# Instancia global del caché
cache_manager = CacheManager()