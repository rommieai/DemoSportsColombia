"""Servicio de caché para resultados de análisis por tiempo de partido"""
from typing import Optional, Dict, Any, List
from collections import OrderedDict
import logging

logger = logging.getLogger(__name__)


class AnalysisCacheService:
    """
    Servicio de caché para almacenar resultados de análisis por tiempo de partido.
    
    Estructura:
    - HashMap (OrderedDict): {tiempo: resultado_completo}
    - Cola (lista): [tiempo1, tiempo2, ...] para mantener orden de inserción
    - Límite: 50 elementos, elimina el más viejo cuando se supera
    """
    
    def __init__(self, max_size: int = 50):
        """
        Inicializa el servicio de caché
        
        Args:
            max_size: Número máximo de elementos en caché (default: 50)
        """
        self.max_size = max_size
        self._cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self._queue: List[str] = []
        logger.info(f"[INFO] AnalysisCacheService inicializado con max_size={max_size}")
    
    def get(self, match_time: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene un resultado del caché por tiempo de partido
        
        Args:
            match_time: Tiempo del partido en formato "M:SS" o "MM:SS"
        
        Returns:
            Diccionario con resultados del análisis, o None si no existe
        """
        result = self._cache.get(match_time)
        if result:
            logger.debug(f"[CACHE HIT] Tiempo {match_time} encontrado en caché")
        else:
            logger.debug(f"[CACHE MISS] Tiempo {match_time} no encontrado en caché")
        return result
    
    def set(self, match_time: str, result: Dict[str, Any]) -> None:
        """
        Almacena un resultado en el caché
        
        Args:
            match_time: Tiempo del partido en formato "M:SS" o "MM:SS"
            result: Diccionario con resultados del análisis
        """
        # Si ya existe, actualizar y reorganizar
        if match_time in self._cache:
            logger.debug(f"[CACHE UPDATE] Actualizando tiempo {match_time}")
            # Mover al final (más reciente)
            self._cache.move_to_end(match_time)
            self._cache[match_time] = result
            # Actualizar posición en cola
            self._queue.remove(match_time)
            self._queue.append(match_time)
            return
        
        # Si llegamos al límite, eliminar el más viejo
        if len(self._cache) >= self.max_size:
            oldest_time = self._queue.pop(0)  # Eliminar de cola
            removed = self._cache.pop(oldest_time, None)  # Eliminar de cache
            logger.info(f"[CACHE EVICTION] Límite alcanzado ({self.max_size}). "
                       f"Eliminado tiempo más viejo: {oldest_time}")
        
        # Agregar nuevo elemento
        self._cache[match_time] = result
        self._queue.append(match_time)
        logger.info(f"[CACHE ADD] Nuevo tiempo agregado: {match_time}. "
                   f"Elementos en caché: {len(self._cache)}/{self.max_size}")
    
    def exists(self, match_time: str) -> bool:
        """
        Verifica si un tiempo existe en el caché
        
        Args:
            match_time: Tiempo del partido en formato "M:SS" o "MM:SS"
        
        Returns:
            True si existe, False si no
        """
        return match_time in self._cache
    
    def clear(self) -> None:
        """Limpia todo el caché"""
        count = len(self._cache)
        self._cache.clear()
        self._queue.clear()
        logger.info(f"[CACHE CLEAR] Caché limpiado. {count} elementos eliminados.")
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Obtiene estadísticas del caché
        
        Returns:
            Diccionario con estadísticas
        """
        return {
            "size": len(self._cache),
            "max_size": self.max_size,
            "usage_percent": (len(self._cache) / self.max_size * 100) if self.max_size > 0 else 0,
            "times_cached": list(self._queue),
            "oldest_time": self._queue[0] if self._queue else None,
            "newest_time": self._queue[-1] if self._queue else None
        }
    
    def get_all_times(self) -> List[str]:
        """
        Obtiene todos los tiempos almacenados en orden
        
        Returns:
            Lista de tiempos en orden de inserción
        """
        return self._queue.copy()
    
    def remove(self, match_time: str) -> bool:
        """
        Elimina manualmente un tiempo del caché
        
        Args:
            match_time: Tiempo del partido a eliminar
        
        Returns:
            True si se eliminó, False si no existía
        """
        if match_time in self._cache:
            self._cache.pop(match_time)
            self._queue.remove(match_time)
            logger.info(f"[CACHE REMOVE] Tiempo {match_time} eliminado manualmente")
            return True
        return False
