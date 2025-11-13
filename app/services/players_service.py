"""Servicio para interactuar con el endpoint de jugadores de API-FOOTBALL"""
import requests
from typing import Dict, Any, List, Optional
from app.core.cache import cache_manager

class PlayersAPIService:
    """Servicio para consultar datos de jugadores de API-FOOTBALL"""
    
    BASE_URL = "https://v3.football.api-sports.io"
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {
            "x-apisports-key": api_key,
            "x-rapidapi-host": "v3.football.api-sports.io"
        }
    
    # ============== SEASONS ==============
    def get_available_seasons(self, player_id: Optional[int] = None) -> List[int]:
        """
        Obtiene todas las temporadas disponibles para estadísticas de jugadores
        
        Args:
            player_id: ID del jugador (opcional, si se omite obtiene todas las temporadas)
        """
        cache_key = f"player_seasons_{player_id or 'all'}"
        cached = cache_manager.get(cache_key, ttl=86400)  # 24 horas
        if cached:
            return cached
        
        url = f"{self.BASE_URL}/players/seasons"
        params = {}
        if player_id:
            params["player"] = player_id
        
        response = requests.get(url, headers=self.headers, params=params, timeout=10)
        data = response.json()
        
        seasons = data.get("response", [])
        cache_manager.set(cache_key, seasons)
        
        return seasons
    
    # ============== PROFILES ==============
    def get_player_profile(self, player_id: int) -> Optional[Dict[str, Any]]:
        """
        Obtiene el perfil de un jugador por ID
        
        Args:
            player_id: ID del jugador
        """
        cache_key = f"player_profile_{player_id}"
        cached = cache_manager.get(cache_key, ttl=604800)  # 7 días
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
        """
        Busca jugadores por nombre (mínimo 3 caracteres)
        
        Args:
            search: Apellido del jugador a buscar
            page: Número de página (250 resultados por página)
        """
        if len(search) < 3:
            return {
                "results": 0,
                "paging": {"current": 1, "total": 0},
                "response": []
            }
        
        cache_key = f"player_search_{search.lower()}_{page}"
        cached = cache_manager.get(cache_key, ttl=3600)  # 1 hora
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
        """
        Obtiene estadísticas de jugadores
        
        Args:
            player_id: ID del jugador
            team_id: ID del equipo
            league_id: ID de la liga
            season: Temporada (YYYY)
            page: Número de página (20 resultados por página)
        """
        params = {"page": page}
        
        if player_id:
            params["id"] = player_id
        if team_id:
            params["team"] = team_id
        if league_id:
            params["league"] = league_id
        if season:
            params["season"] = season
        
        # Generar clave de caché única
        cache_key = f"player_stats_{'_'.join(f'{k}_{v}' for k, v in params.items())}"
        cached = cache_manager.get(cache_key, ttl=3600)  # 1 hora
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
        """
        Busca estadísticas de jugadores por nombre (mínimo 4 caracteres)
        
        Args:
            search: Nombre del jugador
            team_id: ID del equipo
            league_id: ID de la liga
            season: Temporada (YYYY)
        """
        if len(search) < 4:
            return {
                "results": 0,
                "paging": {"current": 1, "total": 0},
                "response": []
            }
        
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
        """
        Obtiene el squad actual de un equipo
        
        Args:
            team_id: ID del equipo
        """
        cache_key = f"team_squad_{team_id}"
        cached = cache_manager.get(cache_key, ttl=604800)  # 7 días
        if cached:
            return cached
        
        url = f"{self.BASE_URL}/players/squads"
        params = {"team": team_id}
        
        response = requests.get(url, headers=self.headers, params=params, timeout=10)
        data = response.json()
        
        cache_manager.set(cache_key, data)
        return data
    
    def get_player_teams(self, player_id: int) -> Dict[str, Any]:
        """
        Obtiene todos los equipos asociados con un jugador
        
        Args:
            player_id: ID del jugador
        """
        cache_key = f"player_teams_{player_id}"
        cached = cache_manager.get(cache_key, ttl=604800)  # 7 días
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
        """
        Obtiene el historial de equipos y temporadas del jugador
        
        Args:
            player_id: ID del jugador
        """
        cache_key = f"player_teams_history_{player_id}"
        cached = cache_manager.get(cache_key, ttl=604800)  # 7 días
        if cached:
            return cached
        
        url = f"{self.BASE_URL}/players/teams"
        params = {"player": player_id}
        
        response = requests.get(url, headers=self.headers, params=params, timeout=10)
        data = response.json()
        
        cache_manager.set(cache_key, data)
        return data
    
    # ============== HELPER METHODS ==============
    @staticmethod
    def get_player_photo_url(player_id: int) -> str:
        """Genera la URL de la foto del jugador"""
        return f"https://media.api-sports.io/football/players/{player_id}.png"
    
    def calculate_totals(self, statistics: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Calcula totales agregados de todas las estadísticas del jugador
        
        Args:
            statistics: Lista de estadísticas por liga/equipo
        """
        totals = {
            "total_goals": 0,
            "total_assists": 0,
            "total_matches": 0,
            "total_minutes": 0,
            "total_yellow_cards": 0,
            "total_red_cards": 0,
            "ratings": []
        }
        
        for stat in statistics:
            games = stat.get("games", {})
            goals = stat.get("goals", {})
            cards = stat.get("cards", {})
            
            totals["total_goals"] += goals.get("total") or 0
            totals["total_assists"] += goals.get("assists") or 0
            totals["total_matches"] += games.get("appearences") or 0
            totals["total_minutes"] += games.get("minutes") or 0
            totals["total_yellow_cards"] += cards.get("yellow") or 0
            totals["total_red_cards"] += cards.get("red") or 0
            
            rating = games.get("rating")
            if rating:
                try:
                    totals["ratings"].append(float(rating))
                except (ValueError, TypeError):
                    pass
        
        # Calcular promedio de rating
        if totals["ratings"]:
            totals["average_rating"] = round(
                sum(totals["ratings"]) / len(totals["ratings"]), 2
            )
        else:
            totals["average_rating"] = None
        
        del totals["ratings"]  # No necesitamos retornar la lista completa
        
        return totals