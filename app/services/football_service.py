"""Servicio para interactuar con API-FOOTBALL"""
import requests
from typing import Dict, Any, List, Optional
from app.core.cache import cache_manager
from app.schemas.football import MatchEvent

class FootballAPIService:
    """Servicio para consultar datos de API-FOOTBALL"""
    
    BASE_URL = "https://v3.football.api-sports.io"
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {
            "x-apisports-key": api_key,
            "x-rapidapi-host": "v3.football.api-sports.io"
        }
    
    def get_live_fixtures(self, use_cache: bool = True) -> Dict[str, Any]:
        """Obtiene todos los partidos en vivo"""
        cache_key = "live_fixtures"
        
        if use_cache:
            cached = cache_manager.get(cache_key, ttl=60)
            if cached:
                return cached
        
        url = f"{self.BASE_URL}/fixtures?live=all"
        response = requests.get(url, headers=self.headers, timeout=10)
        data = response.json()
        
        if use_cache:
            cache_manager.set(cache_key, data)
        
        return data
    def get_fixture_lineups(self, fixture_id: int, use_cache: bool = True) -> List[Dict[str, Any]]:
        """
        Obtiene las alineaciones (lineups) de un partido
        
        Args:
            fixture_id: ID del partido
            use_cache: Usar caché (por defecto True)
        
        Returns:
            Lista con las alineaciones de ambos equipos
        """
        cache_key = f"lineups_{fixture_id}"
        
        if use_cache:
            cached = cache_manager.get(cache_key, ttl=3600)  # 1 hora
            if cached:
                return cached
        
        url = f"{self.BASE_URL}/fixtures/lineups"
        params = {"fixture": fixture_id}
        
        response = requests.get(url, headers=self.headers, params=params, timeout=10)
        data = response.json().get("response", [])
        
        if use_cache:
            cache_manager.set(cache_key, data)
        
        return data
    def get_fixture_by_id(self, fixture_id: int) -> Dict[str, Any]:
        """Obtiene un partido específico por ID"""
        url = f"{self.BASE_URL}/fixtures?id={fixture_id}"
        response = requests.get(url, headers=self.headers, timeout=10)
        return response.json()
    
    def get_fixture_statistics(
        self, 
        fixture_id: int, 
        use_cache: bool = True
    ) -> List[Dict[str, Any]]:
        """Obtiene estadísticas de un partido"""
        if use_cache:
            cached = cache_manager.get_stats(fixture_id, ttl=60)
            if cached:
                return cached
        
        url = f"{self.BASE_URL}/fixtures/statistics?fixture={fixture_id}"
        response = requests.get(url, headers=self.headers, timeout=10)
        data = response.json().get("response", [])
        
        if use_cache:
            cache_manager.set_stats(fixture_id, data)
        
        return data
    
    def get_fixture_events(self, fixture_id: int) -> List[Dict[str, Any]]:
        """Obtiene eventos de un partido"""
        url = f"{self.BASE_URL}/fixtures/events?fixture={fixture_id}"
        response = requests.get(url, headers=self.headers, timeout=10)
        return response.json().get("response", [])
    
    def get_leagues(self) -> Dict[str, Any]:
        """Obtiene todas las ligas disponibles"""
        url = f"{self.BASE_URL}/leagues"
        response = requests.get(url, headers=self.headers, timeout=10)
        return response.json()
    
    @staticmethod
    def normalize_event(event: Dict[str, Any]) -> Dict[str, Any]:
        """Normaliza un evento de la API"""
        time_data = event.get("time", {}) or {}
        team_data = event.get("team", {}) or {}
        player_data = event.get("player", {}) or {}
        
        return {
            "minuto": time_data.get("elapsed"),
            "equipo": team_data.get("name"),
            "jugador": player_data.get("name"),
            "tipo": event.get("type"),
            "detalle": event.get("detail"),
            "_key": (
                time_data.get("elapsed"),
                team_data.get("id"),
                player_data.get("id"),
                event.get("type"),
                event.get("detail")
            )
        }
    
    @staticmethod
    def diff_new_events(fixture_id: int, new_events: List[Dict]) -> List[Dict]:
        """Identifica eventos nuevos comparando con caché"""
        prev_events = cache_manager.get_last_events(fixture_id)
        prev_keys = {e.get("_key") for e in prev_events if e.get("_key")}
        
        new = [e for e in new_events if e.get("_key") not in prev_keys]
        
        if new:
            merged = prev_events + new
            cache_manager.set_last_events(fixture_id, merged)
        
        return new
    
    def format_match_info(self, match_data: Dict[str, Any]) -> Dict[str, Any]:
        """Formatea la información de un partido"""
        fixture = match_data["fixture"]
        league = match_data["league"]
        teams = match_data["teams"]
        goals = match_data["goals"]
        status = fixture["status"]
        
        return {
            "fixture_id": fixture["id"],
            "fecha": fixture["date"],
            "liga": league["name"],
            "pais": league["country"],
            "equipos": {
                "local": teams["home"]["name"],
                "visitante": teams["away"]["name"]
            },
            "marcador": {
                "local": goals["home"],
                "visitante": goals["away"]
            },
            "estado": status["long"],
            "minuto": status["elapsed"]
        }
