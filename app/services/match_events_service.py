"""
Servicio para consultar eventos del partido desde API externa
"""
import httpx
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from functools import lru_cache
import asyncio

class MatchEvent:
    """Representa un evento del partido"""
    def __init__(self, event_type: str, minute: int, team: str, 
                 player: Optional[str] = None, timestamp: Optional[datetime] = None):
        self.event_type = event_type  # "goal", "corner", "foul", etc.
        self.minute = minute
        self.team = team
        self.player = player
        self.timestamp = timestamp or datetime.now()

class MatchEventsService:
    """
    Servicio para conectar con API externa de eventos del partido
    """
    def __init__(self, api_url: str, api_key: Optional[str] = None):
        self.api_url = api_url
        self.api_key = api_key
        self.cache_ttl = 5  # segundos - eventos recientes
        self._cache: Dict[str, tuple[datetime, List[MatchEvent]]] = {}
        
    async def get_recent_events(self, match_id: str, last_minutes: int = 2) -> List[MatchEvent]:
        """
        Obtiene eventos recientes del partido (últimos N minutos)
        
        Args:
            match_id: ID del partido
            last_minutes: Ventana temporal para buscar eventos
        """
        # Verificar cache
        cache_key = f"{match_id}_{last_minutes}"
        if cache_key in self._cache:
            cached_time, cached_events = self._cache[cache_key]
            if (datetime.now() - cached_time).seconds < self.cache_ttl:
                return cached_events
        
        # Consultar API externa
        try:
            async with httpx.AsyncClient() as client:
                headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
                response = await client.get(
                    f"{self.api_url}/matches/{match_id}/events",
                    headers=headers,
                    params={"last_minutes": last_minutes},
                    timeout=5.0
                )
                response.raise_for_status()
                data = response.json()
                
                events = self._parse_events(data)
                self._cache[cache_key] = (datetime.now(), events)
                return events
                
        except Exception as e:
            print(f"Error consultando eventos del partido: {e}")
            return []
    
    def _parse_events(self, data: Dict) -> List[MatchEvent]:
        """
        Parsea la respuesta de la API externa a objetos MatchEvent
        Adaptar según el formato de tu API
        """
        events = []
        for item in data.get("events", []):
            events.append(MatchEvent(
                event_type=item.get("type", "unknown"),
                minute=item.get("minute", 0),
                team=item.get("team", ""),
                player=item.get("player"),
                timestamp=self._parse_timestamp(item.get("timestamp"))
            ))
        return events
    
    def _parse_timestamp(self, ts_str: Optional[str]) -> datetime:
        """Parsea timestamp de la API"""
        if not ts_str:
            return datetime.now()
        try:
            return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except:
            return datetime.now()
    
    async def get_current_match_state(self, match_id: str) -> Dict:
        """
        Obtiene el estado actual del partido (minuto, marcador, etc.)
        """
        try:
            async with httpx.AsyncClient() as client:
                headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
                response = await client.get(
                    f"{self.api_url}/matches/{match_id}",
                    headers=headers,
                    timeout=5.0
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            print(f"Error obteniendo estado del partido: {e}")
            return {"error": str(e)}


class MatchValidator:
    """
    Valida detecciones del modelo contra eventos reales del partido
    """
    def __init__(self, match_events_service: MatchEventsService):
        self.events_service = match_events_service
        
    async def validate_goal_detection(self, match_id: str, detected_team: Optional[str] = None) -> Dict:
        """
        Valida si un gol detectado por el modelo corresponde a un evento real
        
        Returns:
            {
                "is_valid": bool,
                "is_live": bool,
                "match_minute": int,
                "recent_goals": List[Dict],
                "confidence": float
            }
        """
        # Obtener eventos recientes (últimos 2 minutos)
        recent_events = await self.events_service.get_recent_events(match_id, last_minutes=2)
        match_state = await self.events_service.get_current_match_state(match_id)
        
        # Filtrar solo goles
        recent_goals = [e for e in recent_events if e.event_type == "goal"]
        
        # Validar si hay goles recientes
        is_valid = len(recent_goals) > 0
        
        # Verificar si el partido está en vivo
        is_live = match_state.get("status") == "live"
        
        # Calcular confianza basada en timing
        confidence = 1.0 if is_valid else 0.0
        if is_valid and recent_goals:
            # Mayor confianza si el gol fue muy reciente (< 30 segundos)
            latest_goal = recent_goals[0]
            seconds_ago = (datetime.now() - latest_goal.timestamp).seconds
            if seconds_ago < 30:
                confidence = 1.0
            elif seconds_ago < 60:
                confidence = 0.8
            else:
                confidence = 0.6
        
        # Validar equipo si se proporciona
        team_match = False
        if detected_team and recent_goals:
            team_match = any(g.team.lower() == detected_team.lower() for g in recent_goals)
        
        return {
            "is_valid": is_valid,
            "is_live": is_live,
            "is_replay": is_live and not is_valid,  # Está en vivo pero no hay gol reciente
            "match_minute": match_state.get("minute", 0),
            "recent_goals": [
                {
                    "minute": g.minute,
                    "team": g.team,
                    "player": g.player,
                    "seconds_ago": (datetime.now() - g.timestamp).seconds
                }
                for g in recent_goals
            ],
            "confidence": confidence,
            "team_match": team_match if detected_team else None
        }
    
    async def validate_event_detection(self, match_id: str, event_type: str, 
                                      detected_team: Optional[str] = None) -> Dict:
        """
        Valida cualquier tipo de evento detectado (gol, falta, córner, etc.)
        """
        recent_events = await self.events_service.get_recent_events(match_id, last_minutes=2)
        match_state = await self.events_service.get_current_match_state(match_id)
        
        # Filtrar eventos del tipo específico
        matching_events = [e for e in recent_events if e.event_type == event_type]
        
        is_valid = len(matching_events) > 0
        is_live = match_state.get("status") == "live"
        
        return {
            "is_valid": is_valid,
            "is_live": is_live,
            "is_replay": is_live and not is_valid,
            "match_minute": match_state.get("minute", 0),
            "matching_events": [
                {
                    "minute": e.minute,
                    "team": e.team,
                    "player": e.player
                }
                for e in matching_events
            ]
        }