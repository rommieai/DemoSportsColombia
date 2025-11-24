"""Servicio para interactuar con API-FOOTBALL (jugadores)"""
import requests
from typing import Dict, Any, List, Optional
from app.core.cache import cache_manager


class PlayersAPIService:
    """Cliente HTTP para el endpoint de jugadores de API-FOOTBALL"""
    
    BASE_URL = "https://v3.football.api-sports.io"
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {
            "x-apisports-key": api_key,
            "x-rapidapi-host": "v3.football.api-sports.io"
        }
    
    # ============== SEASONS ==============
    def get_available_seasons(self, player_id: Optional[int] = None) -> List[int]:
        """Obtiene temporadas disponibles para estadísticas de jugadores"""
        cache_key = f"player_seasons_{player_id or 'all'}"
        cached = cache_manager.get(cache_key, ttl=86400)
        if cached:
            return cached
        
        url = f"{self.BASE_URL}/players/seasons"
        params = {"player": player_id} if player_id else {}
        
        response = requests.get(url, headers=self.headers, params=params, timeout=10)
        data = response.json()
        
        seasons = data.get("response", [])
        cache_manager.set(cache_key, seasons)
        return seasons
    
    # ============== PROFILES ==============
    def get_player_profile(self, player_id: int) -> Optional[Dict[str, Any]]:
        """Obtiene el perfil completo de un jugador"""
        cache_key = f"player_profile_{player_id}"
        cached = cache_manager.get(cache_key, ttl=604800)
        if cached:
            return cached
        
        url = f"{self.BASE_URL}/players/profiles"
        params = {"player": player_id}
        
        response = requests.get(url, headers=self.headers, params=params, timeout=10)
        data = response.json()
        
        if data.get("results", 0) > 0:
            profile = data["response"][0]
            cache_manager.set(cache_key, profile)
            return profile
        
        return None
    
    def search_players(self, search: str, page: int = 1) -> Dict[str, Any]:
        """Busca jugadores por nombre"""
        if len(search) < 3:
            return {"results": 0, "paging": {"current": 1, "total": 0}, "response": []}
        
        cache_key = f"player_search_{search.lower()}_{page}"
        cached = cache_manager.get(cache_key, ttl=3600)
        if cached:
            return cached
        
        url = f"{self.BASE_URL}/players/profiles"
        params = {"search": search, "page": page}
        
        response = requests.get(url, headers=self.headers, params=params, timeout=10)
        data = response.json()
        
        cache_manager.set(cache_key, data)
        return data
    
    # ============== STATISTICS ==============
    def get_player_statistics(
        self,
        player_id: Optional[int] = None,
        team_id: Optional[int] = None,
        league_id: Optional[int] = None,
        season: Optional[int] = None,
        page: int = 1
    ) -> Dict[str, Any]:
        """Obtiene estadísticas de jugadores"""
        params = {"page": page}
        
        if player_id:
            params["id"] = player_id
        if team_id:
            params["team"] = team_id
        if league_id:
            params["league"] = league_id
        if season:
            params["season"] = season
        
        cache_key = f"player_stats_{'_'.join(f'{k}_{v}' for k, v in params.items())}"
        cached = cache_manager.get(cache_key, ttl=3600)
        if cached:
            return cached
        
        url = f"{self.BASE_URL}/players"
        response = requests.get(url, headers=self.headers, params=params, timeout=10)
        data = response.json()
        
        cache_manager.set(cache_key, data)
        return data
    
    def search_player_stats(
        self,
        search: str,
        team_id: Optional[int] = None,
        league_id: Optional[int] = None,
        season: Optional[int] = None
    ) -> Dict[str, Any]:
        """Busca estadísticas por nombre (mínimo 4 caracteres)"""
        if len(search) < 4:
            return {"results": 0, "paging": {"current": 1, "total": 0}, "response": []}
        
        params = {"search": search}
        if team_id:
            params["team"] = team_id
        elif league_id:
            params["league"] = league_id
        if season:
            params["season"] = season
        
        cache_key = f"player_stats_search_{'_'.join(f'{k}_{v}' for k, v in params.items())}"
        cached = cache_manager.get(cache_key, ttl=3600)
        if cached:
            return cached
        
        url = f"{self.BASE_URL}/players"
        response = requests.get(url, headers=self.headers, params=params, timeout=10)
        data = response.json()
        
        cache_manager.set(cache_key, data)
        return data
    
    # ============== SQUADS ==============
    def get_team_squad(self, team_id: int) -> Dict[str, Any]:
        """Obtiene el squad actual de un equipo"""
        cache_key = f"team_squad_{team_id}"
        cached = cache_manager.get(cache_key, ttl=604800)
        if cached:
            return cached
        
        url = f"{self.BASE_URL}/players/squads"
        params = {"team": team_id}
        
        response = requests.get(url, headers=self.headers, params=params, timeout=10)
        data = response.json()
        
        cache_manager.set(cache_key, data)
        return data
    
    def get_player_teams(self, player_id: int) -> Dict[str, Any]:
        """Obtiene todos los equipos del jugador"""
        cache_key = f"player_teams_{player_id}"
        cached = cache_manager.get(cache_key, ttl=604800)
        if cached:
            return cached
        
        url = f"{self.BASE_URL}/players/squads"
        params = {"player": player_id}
        
        response = requests.get(url, headers=self.headers, params=params, timeout=10)
        data = response.json()
        
        cache_manager.set(cache_key, data)
        return data
    
    # ============== PLAYER TEAMS HISTORY ==============
    def get_player_teams_history(self, player_id: int) -> Dict[str, Any]:
        """Obtiene historial de equipos del jugador"""
        cache_key = f"player_teams_history_{player_id}"
        cached = cache_manager.get(cache_key, ttl=604800)
        if cached:
            return cached
        
        url = f"{self.BASE_URL}/players/teams"
        params = {"player": player_id}
        
        response = requests.get(url, headers=self.headers, params=params, timeout=10)
        data = response.json()
        
        cache_manager.set(cache_key, data)
        return data
    
    # ============== HELPERS ==============
    @staticmethod
    def get_player_photo_url(player_id: int) -> str:
        """Genera URL de foto del jugador"""
        return f"https://media.api-sports.io/football/players/{player_id}.png"