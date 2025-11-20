"""Sistema de caché para la API de fútbol"""
import time
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import hashlib
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


class TTLCache:
    def __init__(self):
        self.store = {}  # { key: (timestamp, value) }

    def get(self, key):
        if key not in self.store:
            return None
        
        ts, value = self.store[key]
        # 10 segundos de TTL
        if time.time() - ts > 10:
            return None  # expiró

        return value

    def set(self, key, value):
        self.store[key] = (time.time(), value)


cache_api = TTLCache()


class TTLCache:
    """Cache con Time-To-Live (TTL)"""
    
    def __init__(self, ttl_seconds: int = 10):
        self.store: Dict[str, tuple[float, Any]] = {}
        self.ttl = ttl_seconds

    def get(self, key: str) -> Optional[Any]:
        """Obtiene un valor del cache si no ha expirado"""
        if key not in self.store:
            return None
        
        timestamp, value = self.store[key]
        if time.time() - timestamp > self.ttl:
            del self.store[key]
            return None
        
        return value

    def set(self, key: str, value: Any) -> None:
        """Guarda un valor en el cache con timestamp actual"""
        self.store[key] = (time.time(), value)

    def delete(self, key: str) -> None:
        """Elimina un valor del cache"""
        if key in self.store:
            del self.store[key]

    def clear(self) -> None:
        """Limpia todo el cache"""
        self.store.clear()


class CommentCache:
    """Cache específico para comentarios con hash para evitar repeticiones"""
    
    def __init__(self, ttl_seconds: int = 60):
        self.store: Dict[int, tuple[float, str, str]] = {}  # match_id: (timestamp, hash, comentario)
        self.ttl = ttl_seconds

    def get(self, match_id: int) -> Optional[str]:
        """Obtiene un comentario si no ha expirado"""
        if match_id not in self.store:
            return None
        
        timestamp, _, comentario = self.store[match_id]
        if time.time() - timestamp > self.ttl:
            del self.store[match_id]
            return None
        
        return comentario

    def set(self, match_id: int, comentario: str) -> None:
        """Guarda un comentario con su hash"""
        hash_comment = hashlib.md5(comentario.encode()).hexdigest()
        self.store[match_id] = (time.time(), hash_comment, comentario)

    def get_last_hash(self, match_id: int) -> Optional[str]:
        """Obtiene el hash del último comentario"""
        if match_id not in self.store:
            return None
        return self.store[match_id][1]


class EventsCache:
    """Cache para manejar eventos de partidos y detectar cambios"""
    
    def __init__(self):
        self.last_events: Dict[int, List[Dict[str, Any]]] = {}

    def get_last_events(self, fixture_id: int) -> List[Dict[str, Any]]:
        """Obtiene los últimos eventos de un fixture"""
        return self.last_events.get(fixture_id, [])

    def set_last_events(self, fixture_id: int, events: List[Dict[str, Any]]) -> None:
        """Guarda los eventos de un fixture"""
        self.last_events[fixture_id] = events

    def has_new_events(self, fixture_id: int, current_events: List[Dict[str, Any]]) -> bool:
        """Detecta si hay eventos nuevos"""
        last = self.get_last_events(fixture_id)
        return len(current_events) > len(last)

    def get_new_events(self, fixture_id: int, current_events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Obtiene solo los eventos nuevos"""
        baseline = self.get_last_events(fixture_id)
        return [e for e in current_events if e not in baseline]


class TriviaCache:
    """Cache para trivia con expiración larga"""
    
    def __init__(self, ttl_seconds: int = 60 * 60 * 2):  # 2 horas
        self.store: Dict[str, tuple[float, List[Dict[str, Any]]]] = {}
        self.ttl = ttl_seconds

    def _make_key(self, team1: str, team2: str) -> str:
        """Genera clave de cache normalizando nombres"""
        return f"{team1.lower()}_{team2.lower()}"

    def get(self, team1: str, team2: str) -> Optional[List[Dict[str, Any]]]:
        """Obtiene trivia si no ha expirado"""
        key = self._make_key(team1, team2)
        
        if key not in self.store:
            return None
        
        timestamp, data = self.store[key]
        if time.time() - timestamp > self.ttl:
            del self.store[key]
            return None
        
        return data

    def set(self, team1: str, team2: str, questions: List[Dict[str, Any]]) -> None:
        """Guarda trivia en cache"""
        key = self._make_key(team1, team2)
        self.store[key] = (time.time(), questions)


class MatchDataCache:
    """Cache para información completa de partidos"""
    
    def __init__(self, ttl_seconds: int = 60):
        self.store: Dict[int, tuple[float, Dict[str, Any]]] = {}
        self.ttl = ttl_seconds

    def get(self, match_id: int) -> Optional[Dict[str, Any]]:
        """Obtiene datos completos de un partido"""
        if match_id not in self.store:
            return None
        
        timestamp, data = self.store[match_id]
        if time.time() - timestamp > self.ttl:
            del self.store[match_id]
            return None
        
        return data

    def set(self, match_id: int, data: Dict[str, Any]) -> None:
        """Guarda datos completos de un partido"""
        self.store[match_id] = (time.time(), data)


# ===== INSTANCIAS GLOBALES =====
# Cache para eventos con TTL corto (10 segundos)
events_cache = TTLCache(ttl_seconds=10)

# Cache para eventos históricos (detección de cambios)
events_history = EventsCache()

# Cache para comentarios (60 segundos)
comment_cache = CommentCache(ttl_seconds=60)

# Cache para datos completos de partidos
match_data_cache = MatchDataCache(ttl_seconds=60)

# Cache para trivia (2 horas)
trivia_cache = TriviaCache(ttl_seconds=60 * 60 * 2)


