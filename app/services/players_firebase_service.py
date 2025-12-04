"""Servicio de jugadores con integración Firebase - Reemplaza cache en memoria"""
import requests
from typing import Dict, Any, List, Optional
from app.services.firebase_service import firebase_service


class PlayersFirebaseService:
    """Servicio para consultar datos de jugadores con almacenamiento en Firebase"""
    
    BASE_URL = "https://v3.football.api-sports.io"
    
    # ===== COLECCIONES DE FIREBASE =====
    COLLECTION_PLAYER_PROFILES = "player_profiles"
    COLLECTION_PLAYER_SEASONS = "player_seasons"
    COLLECTION_PLAYER_SEARCH = "player_search"
    COLLECTION_PLAYER_STATS = "player_statistics"
    COLLECTION_TEAM_SQUADS = "team_squads"
    COLLECTION_PLAYER_TEAMS = "player_teams"
    COLLECTION_PLAYER_TEAMS_HISTORY = "player_teams_history"
    COLLECTION_QUICK_STATS = "player_quick_stats"  # Para endpoint optimizado
    COLLECTION_PLAYER_NEWS = "player_news"  # Para noticias de jugadores
    
    # ===== TTL POR TIPO DE DATO (en segundos) =====
    TTL_PROFILES = 604800      # 7 días (perfil no cambia frecuentemente)
    TTL_SEASONS = 86400        # 1 día (temporadas disponibles son estables)
    TTL_SEARCH = 3600          # 1 hora (búsquedas de jugadores)
    TTL_STATS = 3600           # 1 hora (estadísticas pueden actualizarse)
    TTL_SQUADS = 604800        # 7 días (plantillas cambian poco)
    TTL_TEAMS = 604800         # 7 días (historial de equipos es estático)
    TTL_QUICK_STATS = 7200     # 2 horas (para endpoint quick-stats)
    TTL_NEWS = 86400           # 1 día (noticias frescas pero no en tiempo real)
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {
            "x-apisports-key": api_key,
            "x-rapidapi-host": "v3.football.api-sports.io"
        }
        self.fb = firebase_service
    
    # ===== TEMPORADAS =====
    
    def get_available_seasons(
        self, 
        player_id: Optional[int] = None,
        force_refresh: bool = False
    ) -> List[int]:
        """
        Obtiene temporadas disponibles para estadísticas de jugadores
        
        Args:
            player_id: ID del jugador (opcional)
            force_refresh: Forzar llamada a API
        """
        doc_id = f"seasons_{player_id or 'all'}"
        
        # Intentar obtener de Firebase
        if not force_refresh:
            cached_data = self.fb.get_if_valid(self.COLLECTION_PLAYER_SEASONS, doc_id)
            if cached_data:
                print(f"✓ Temporadas jugador {player_id or 'all'} obtenidas de Firebase")
                return cached_data
        
        # Llamar a API externa
        print(f"⚡ Llamando a API externa: temporadas jugador {player_id or 'all'}")
        url = f"{self.BASE_URL}/players/seasons"
        params = {"player": player_id} if player_id else {}
        
        response = requests.get(url, headers=self.headers, params=params, timeout=10)
        data = response.json()
        
        seasons = data.get("response", [])
        
        # Guardar en Firebase
        self.fb.set_with_ttl(
            self.COLLECTION_PLAYER_SEASONS,
            doc_id,
            seasons,
            self.TTL_SEASONS
        )
        
        return seasons
    
    # ===== PERFILES =====
    
    def get_player_profile(
        self, 
        player_id: int,
        force_refresh: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        Obtiene el perfil completo de un jugador
        
        Args:
            player_id: ID del jugador
            force_refresh: Forzar llamada a API
        """
        doc_id = f"profile_{player_id}"
        
        if not force_refresh:
            cached_data = self.fb.get_if_valid(self.COLLECTION_PLAYER_PROFILES, doc_id)
            if cached_data:
                print(f"✓ Perfil jugador {player_id} obtenido de Firebase")
                return cached_data
        
        print(f"⚡ Llamando a API externa: perfil jugador {player_id}")
        url = f"{self.BASE_URL}/players/profiles"
        params = {"player": player_id}
        
        response = requests.get(url, headers=self.headers, params=params, timeout=10)
        data = response.json()
        
        if data.get("results", 0) > 0:
            profile = data["response"][0]
            
            # Guardar en Firebase
            self.fb.set_with_ttl(
                self.COLLECTION_PLAYER_PROFILES,
                doc_id,
                profile,
                self.TTL_PROFILES
            )
            
            return profile
        
        return None
    
    def search_players(
        self, 
        search: str, 
        page: int = 1,
        force_refresh: bool = False
    ) -> Dict[str, Any]:
        """
        Busca jugadores por nombre
        
        Args:
            search: Nombre a buscar
            page: Número de página
            force_refresh: Forzar llamada a API
        """
        if len(search) < 3:
            return {"results": 0, "paging": {"current": 1, "total": 0}, "response": []}
        
        doc_id = f"search_{search.lower().strip()}_{page}"
        
        if not force_refresh:
            cached_data = self.fb.get_if_valid(self.COLLECTION_PLAYER_SEARCH, doc_id)
            if cached_data:
                print(f"✓ Búsqueda '{search}' (página {page}) obtenida de Firebase")
                return cached_data
        
        print(f"⚡ Llamando a API externa: búsqueda '{search}' página {page}")
        url = f"{self.BASE_URL}/players/profiles"
        params = {"search": search, "page": page}
        
        response = requests.get(url, headers=self.headers, params=params, timeout=10)
        data = response.json()
        
        # Guardar en Firebase
        self.fb.set_with_ttl(
            self.COLLECTION_PLAYER_SEARCH,
            doc_id,
            data,
            self.TTL_SEARCH
        )
        
        return data
    
    # ===== ESTADÍSTICAS =====
    
    def get_player_statistics(
        self,
        player_id: Optional[int] = None,
        team_id: Optional[int] = None,
        league_id: Optional[int] = None,
        season: Optional[int] = None,
        page: int = 1,
        force_refresh: bool = False
    ) -> Dict[str, Any]:
        """
        Obtiene estadísticas de jugadores
        
        Args:
            player_id: ID del jugador
            team_id: ID del equipo
            league_id: ID de la liga
            season: Temporada
            page: Número de página
            force_refresh: Forzar llamada a API
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
        
        # Generar clave única
        doc_id = f"stats_{'_'.join(f'{k}_{v}' for k, v in sorted(params.items()))}"
        
        if not force_refresh:
            cached_data = self.fb.get_if_valid(self.COLLECTION_PLAYER_STATS, doc_id)
            if cached_data:
                print(f"✓ Estadísticas obtenidas de Firebase (cache hit)")
                return cached_data
        
        print(f"⚡ Llamando a API externa: estadísticas jugador")
        url = f"{self.BASE_URL}/players"
        response = requests.get(url, headers=self.headers, params=params, timeout=10)
        data = response.json()
        
        # Guardar en Firebase
        self.fb.set_with_ttl(
            self.COLLECTION_PLAYER_STATS,
            doc_id,
            data,
            self.TTL_STATS
        )
        
        return data
    
    def search_player_stats(
        self,
        search: str,
        team_id: Optional[int] = None,
        league_id: Optional[int] = None,
        season: Optional[int] = None,
        force_refresh: bool = False
    ) -> Dict[str, Any]:
        """
        Busca estadísticas por nombre (mínimo 4 caracteres)
        
        Args:
            search: Nombre del jugador
            team_id: ID del equipo
            league_id: ID de la liga
            season: Temporada
            force_refresh: Forzar llamada a API
        """
        if len(search) < 4:
            return {"results": 0, "paging": {"current": 1, "total": 0}, "response": []}
        
        params = {"search": search}
        if team_id:
            params["team"] = team_id
        elif league_id:
            params["league"] = league_id
        if season:
            params["season"] = season
        
        doc_id = f"stats_search_{'_'.join(f'{k}_{v}' for k, v in sorted(params.items()))}"
        
        if not force_refresh:
            cached_data = self.fb.get_if_valid(self.COLLECTION_PLAYER_STATS, doc_id)
            if cached_data:
                print(f"✓ Búsqueda de estadísticas obtenida de Firebase")
                return cached_data
        
        print(f"⚡ Llamando a API externa: búsqueda estadísticas '{search}'")
        url = f"{self.BASE_URL}/players"
        response = requests.get(url, headers=self.headers, params=params, timeout=10)
        data = response.json()
        
        # Guardar en Firebase
        self.fb.set_with_ttl(
            self.COLLECTION_PLAYER_STATS,
            doc_id,
            data,
            self.TTL_STATS
        )
        
        return data
    
    # ===== PLANTILLAS (SQUADS) =====
    
    def get_team_squad(
        self, 
        team_id: int,
        force_refresh: bool = False
    ) -> Dict[str, Any]:
        """
        Obtiene el squad actual de un equipo
        
        Args:
            team_id: ID del equipo
            force_refresh: Forzar llamada a API
        """
        doc_id = f"squad_{team_id}"
        
        if not force_refresh:
            cached_data = self.fb.get_if_valid(self.COLLECTION_TEAM_SQUADS, doc_id)
            if cached_data:
                print(f"✓ Squad equipo {team_id} obtenido de Firebase")
                return cached_data
        
        print(f"⚡ Llamando a API externa: squad equipo {team_id}")
        url = f"{self.BASE_URL}/players/squads"
        params = {"team": team_id}
        
        response = requests.get(url, headers=self.headers, params=params, timeout=10)
        data = response.json()
        
        # Guardar en Firebase
        self.fb.set_with_ttl(
            self.COLLECTION_TEAM_SQUADS,
            doc_id,
            data,
            self.TTL_SQUADS
        )
        
        return data
    
    def get_player_teams(
        self, 
        player_id: int,
        force_refresh: bool = False
    ) -> Dict[str, Any]:
        """
        Obtiene todos los equipos del jugador
        
        Args:
            player_id: ID del jugador
            force_refresh: Forzar llamada a API
        """
        doc_id = f"teams_{player_id}"
        
        if not force_refresh:
            cached_data = self.fb.get_if_valid(self.COLLECTION_PLAYER_TEAMS, doc_id)
            if cached_data:
                print(f"✓ Equipos jugador {player_id} obtenidos de Firebase")
                return cached_data
        
        print(f"⚡ Llamando a API externa: equipos jugador {player_id}")
        url = f"{self.BASE_URL}/players/squads"
        params = {"player": player_id}
        
        response = requests.get(url, headers=self.headers, params=params, timeout=10)
        data = response.json()
        
        # Guardar en Firebase
        self.fb.set_with_ttl(
            self.COLLECTION_PLAYER_TEAMS,
            doc_id,
            data,
            self.TTL_TEAMS
        )
        
        return data
    
    # ===== HISTORIAL DE EQUIPOS =====
    
    def get_player_teams_history(
        self, 
        player_id: int,
        force_refresh: bool = False
    ) -> Dict[str, Any]:
        """
        Obtiene historial de equipos del jugador
        
        Args:
            player_id: ID del jugador
            force_refresh: Forzar llamada a API
        """
        doc_id = f"history_{player_id}"
        
        if not force_refresh:
            cached_data = self.fb.get_if_valid(self.COLLECTION_PLAYER_TEAMS_HISTORY, doc_id)
            if cached_data:
                print(f"✓ Historial jugador {player_id} obtenido de Firebase")
                return cached_data
        
        print(f"⚡ Llamando a API externa: historial jugador {player_id}")
        url = f"{self.BASE_URL}/players/teams"
        params = {"player": player_id}
        
        response = requests.get(url, headers=self.headers, params=params, timeout=10)
        data = response.json()
        
        # Guardar en Firebase
        self.fb.set_with_ttl(
            self.COLLECTION_PLAYER_TEAMS_HISTORY,
            doc_id,
            data,
            self.TTL_TEAMS
        )
        
        return data
    
    # ===== MÉTODOS OPTIMIZADOS =====
    
    def get_quick_stats_cached(
        self,
        name: str,
        season: Optional[int],
        nationality: Optional[str],
        computed_result: Dict[str, Any]
    ) -> None:
        """
        Guarda resultado de quick-stats en Firebase
        
        Este método se usa DESPUÉS de calcular el resultado completo
        para evitar recalcularlo en futuras peticiones.
        
        Args:
            name: Nombre del jugador
            season: Temporada
            nationality: Nacionalidad (opcional)
            computed_result: Resultado ya calculado
        """
        doc_id = f"quick_{name.lower().strip()}_{season or 'latest'}_{(nationality or '').lower().strip()}"
        
        self.fb.set_with_ttl(
            self.COLLECTION_QUICK_STATS,
            doc_id,
            computed_result,
            self.TTL_QUICK_STATS
        )
        
        print(f"✓ Quick stats guardadas en Firebase: {doc_id}")
    
    def get_quick_stats_from_cache(
        self,
        name: str,
        season: Optional[int],
        nationality: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        """
        Intenta obtener quick-stats desde Firebase
        
        Args:
            name: Nombre del jugador
            season: Temporada
            nationality: Nacionalidad (opcional)
            
        Returns:
            Resultado en cache o None
        """
        doc_id = f"quick_{name.lower().strip()}_{season or 'latest'}_{(nationality or '').lower().strip()}"
        
        cached = self.fb.get_if_valid(self.COLLECTION_QUICK_STATS, doc_id)
        
        if cached:
            print(f"✓ Quick stats obtenidas de Firebase: {doc_id}")
        
        return cached
    
    # ===== HELPERS =====
    
    @staticmethod
    def get_player_photo_url(player_id: int) -> str:
        """Genera URL de foto del jugador"""
        return f"https://media.api-sports.io/football/players/{player_id}.png"
    
    # ===== NOTICIAS DE JUGADORES =====
    
    def get_player_news_from_cache(
        self,
        player_name: str
    ) -> Optional[Dict[str, Any]]:
        """
        Intenta obtener noticias del jugador desde Firebase
        
        Args:
            player_name: Nombre completo del jugador
            
        Returns:
            Noticias en cache o None si no existen o expiraron
        """
        # Normalizar nombre para la clave (sin espacios, minúsculas)
        doc_id = f"news_{player_name.lower().strip().replace(' ', '_')}"
        
        cached = self.fb.get_if_valid(self.COLLECTION_PLAYER_NEWS, doc_id)
        
        if cached:
            print(f"✓ Noticias de '{player_name}' obtenidas de Firebase")
        
        return cached
    
    def set_player_news_cache(
        self,
        player_name: str,
        news_data: Dict[str, Any]
    ) -> None:
        """
        Guarda noticias de un jugador en Firebase
        
        Si ya existe una entrada expirada, Firebase la eliminará automáticamente
        al intentar recuperarla (método get_if_valid)
        
        Args:
            player_name: Nombre completo del jugador
            news_data: Datos de la noticia ya generados
        """
        doc_id = f"news_{player_name.lower().strip().replace(' ', '_')}"
        
        self.fb.set_with_ttl(
            self.COLLECTION_PLAYER_NEWS,
            doc_id,
            news_data,
            self.TTL_NEWS
        )
        
        print(f"✓ Noticias de '{player_name}' guardadas en Firebase (TTL: 24h)")
    
    # ===== LIMPIEZA (opcional, para mantenimiento) =====
    
    def cleanup_expired_data(self) -> Dict[str, int]:
        """
        Limpia datos expirados de todas las colecciones
        
        Returns:
            Dict con cantidad de documentos eliminados por colección
        """
        collections = [
            self.COLLECTION_PLAYER_PROFILES,
            self.COLLECTION_PLAYER_SEASONS,
            self.COLLECTION_PLAYER_SEARCH,
            self.COLLECTION_PLAYER_STATS,
            self.COLLECTION_TEAM_SQUADS,
            self.COLLECTION_PLAYER_TEAMS,
            self.COLLECTION_PLAYER_TEAMS_HISTORY,
            self.COLLECTION_QUICK_STATS,
            self.COLLECTION_PLAYER_NEWS  # ✅ Incluir noticias en limpieza
        ]
        
        results = {}
        for collection in collections:
            count = self.fb.cleanup_expired(collection)
            results[collection] = count
            if count > 0:
                print(f"✓ Limpiados {count} documentos expirados de {collection}")
        
        return results