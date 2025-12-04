"""Servicio de fútbol con integración Firebase - Reemplaza el cache en memoria"""
import requests
from typing import Dict, Any, List, Optional
from datetime import datetime
from app.services.firebase_service import firebase_service

class FootballFirebaseService:
    """Servicio para consultar datos de API-FOOTBALL con almacenamiento en Firebase"""
    
    BASE_URL = "https://v3.football.api-sports.io"
    
    # Colecciones de Firebase
    COLLECTION_LIVE_FIXTURES = "live_fixtures"
    COLLECTION_FIXTURES = "fixtures"
    COLLECTION_LINEUPS = "lineups"
    COLLECTION_STATISTICS = "statistics"
    COLLECTION_EVENTS = "events"
    COLLECTION_TEAM_STATS = "team_statistics"
    COLLECTION_TEAM_SEASONS = "team_seasons"
    
    # TTL por tipo de dato (en segundos)
    TTL_LIVE_FIXTURES = 60  # 1 minuto
    TTL_FIXTURE_DETAILS = 300  # 5 minutos
    TTL_LINEUPS = 3600  # 1 hora (no cambian durante el partido)
    TTL_STATISTICS = 60  # 1 minuto
    TTL_EVENTS = 60  # 1 minuto
    TTL_TEAM_STATS = 7200  # 2 horas
    TTL_TEAM_SEASONS = 7200  # 2 horas
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {
            "x-apisports-key": api_key,
            "x-rapidapi-host": "v3.football.api-sports.io"
        }
        self.fb = firebase_service
    
    # ===== PARTIDOS EN VIVO =====
    
    def get_live_fixtures(self, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Obtiene todos los partidos en vivo
        
        Args:
            force_refresh: Si True, fuerza llamada a la API
        
        Returns:
            Datos de partidos en vivo
        """
        doc_id = "current"
        
        # Intentar obtener de Firebase primero
        if not force_refresh:
            cached_data = self.fb.get_if_valid(self.COLLECTION_LIVE_FIXTURES, doc_id)
            if cached_data:
                print(f"✓ Live fixtures obtenidos de Firebase (cache hit)")
                return cached_data
        
        # Si no hay cache o se fuerza refresh, llamar a la API
        print(f"⚡ Llamando a API externa: live fixtures")
        url = f"{self.BASE_URL}/fixtures?live=all"
        response = requests.get(url, headers=self.headers, timeout=10)
        data = response.json()
        
        # Guardar en Firebase
        self.fb.set_with_ttl(self.COLLECTION_LIVE_FIXTURES, doc_id, data, self.TTL_LIVE_FIXTURES)
        
        return data
    
    # ===== FIXTURE POR ID =====
    
    def get_fixture_by_id(self, fixture_id: int, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Obtiene un partido específico por ID
        
        Args:
            fixture_id: ID del partido
            force_refresh: Si True, fuerza llamada a la API
        """
        doc_id = f"fixture_{fixture_id}"
        
        if not force_refresh:
            cached_data = self.fb.get_if_valid(self.COLLECTION_FIXTURES, doc_id)
            if cached_data:
                print(f"✓ Fixture {fixture_id} obtenido de Firebase")
                return cached_data
        
        print(f"⚡ Llamando a API externa: fixture {fixture_id}")
        url = f"{self.BASE_URL}/fixtures?id={fixture_id}"
        response = requests.get(url, headers=self.headers, timeout=10)
        data = response.json()
        
        # Determinar TTL basado en estado del partido
        ttl = self._get_dynamic_ttl(data)
        self.fb.set_with_ttl(self.COLLECTION_FIXTURES, doc_id, data, ttl)
        
        return data
    
    def _get_dynamic_ttl(self, fixture_data: Dict[str, Any]) -> int:
        """
        Determina TTL dinámico basado en el estado del partido
        
        - Partido en vivo: 60 segundos
        - Partido finalizado: 1 hora (datos no cambian)
        - Partido futuro: 5 minutos
        """
        if not fixture_data.get("response"):
            return self.TTL_FIXTURE_DETAILS
        
        status = fixture_data["response"][0]["fixture"]["status"]["short"]
        
        # Partido en vivo (1H, 2H, HT, ET, P, etc.)
        if status in ["1H", "2H", "HT", "ET", "P", "BT", "LIVE"]:
            return 60
        
        # Partido finalizado (FT, AET, PEN, etc.)
        if status in ["FT", "AET", "PEN"]:
            return 3600
        
        # Partido futuro o suspendido
        return self.TTL_FIXTURE_DETAILS
    
    # ===== ESTADÍSTICAS DE PARTIDO =====
    
    def get_fixture_statistics(
        self, 
        fixture_id: int, 
        force_refresh: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Obtiene estadísticas de un partido
        
        Args:
            fixture_id: ID del partido
            force_refresh: Si True, fuerza llamada a la API
        """
        doc_id = f"stats_{fixture_id}"
        
        if not force_refresh:
            cached_data = self.fb.get_if_valid(self.COLLECTION_STATISTICS, doc_id)
            if cached_data:
                print(f"✓ Estadísticas {fixture_id} obtenidas de Firebase")
                return cached_data.get("response", [])
        
        print(f"⚡ Llamando a API externa: estadísticas {fixture_id}")
        url = f"{self.BASE_URL}/fixtures/statistics?fixture={fixture_id}"
        response = requests.get(url, headers=self.headers, timeout=10)
        data = response.json()
        
        self.fb.set_with_ttl(
            self.COLLECTION_STATISTICS, 
            doc_id, 
            data, 
            self.TTL_STATISTICS
        )
        
        return data.get("response", [])
    
    # ===== EVENTOS DE PARTIDO =====
        
    def get_fixture_events(
        self, 
        fixture_id: int, 
        force_refresh: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Obtiene eventos de un partido
        
        Args:
            fixture_id: ID del partido
            force_refresh: Si True, fuerza llamada a la API
        
        Returns:
            Lista de eventos en formato RAW de la API (sin normalizar)
        """
        doc_id = f"events_{fixture_id}"
        
        if not force_refresh:
            cached_data = self.fb.get_if_valid(self.COLLECTION_EVENTS, doc_id)
            if cached_data:
                print(f"✓ Eventos {fixture_id} obtenidos de Firebase")
                # Asegurar que devolvemos la estructura correcta
                if isinstance(cached_data, dict) and "response" in cached_data:
                    return cached_data.get("response", [])
                elif isinstance(cached_data, list):
                    # Si por alguna razón guardamos la lista directamente
                    return cached_data
                else:
                    print(f"⚠️ Datos de eventos en formato inesperado: {type(cached_data)}")
                    # Forzar recarga desde API
                    force_refresh = True
        
        if force_refresh or not cached_data:
            print(f"⚡ Llamando a API externa: eventos {fixture_id}")
            url = f"{self.BASE_URL}/fixtures/events?fixture={fixture_id}"
            response = requests.get(url, headers=self.headers, timeout=10)
            data = response.json()
            
            self.fb.set_with_ttl(
                self.COLLECTION_EVENTS, 
                doc_id, 
                data,  # Guardar el objeto completo con 'response'
                self.TTL_EVENTS
            )
            
            return data.get("response", [])
        
        return []    
        # ===== ALINEACIONES =====
    
    def get_fixture_lineups(
        self, 
        fixture_id: int, 
        force_refresh: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Obtiene las alineaciones de un partido
        
        Args:
            fixture_id: ID del partido
            force_refresh: Si True, fuerza llamada a la API
        """
        doc_id = f"lineup_{fixture_id}"
        
        if not force_refresh:
            cached_data = self.fb.get_if_valid(self.COLLECTION_LINEUPS, doc_id)
            if cached_data:
                print(f"✓ Alineaciones {fixture_id} obtenidas de Firebase")
                return cached_data.get("response", [])
        
        print(f"⚡ Llamando a API externa: alineaciones {fixture_id}")
        url = f"{self.BASE_URL}/fixtures/lineups"
        params = {"fixture": fixture_id}
        response = requests.get(url, headers=self.headers, params=params, timeout=10)
        data = response.json()
        
        self.fb.set_with_ttl(
            self.COLLECTION_LINEUPS, 
            doc_id, 
            data, 
            self.TTL_LINEUPS
        )
        
        return data.get("response", [])
    
    # ===== PARTIDOS POR FECHA =====
    
    def get_fixtures_by_date(
        self, 
        fecha: str, 
        timezone: str = None,
        force_refresh: bool = False
    ) -> Dict[str, Any]:
        """
        Obtiene todos los partidos programados para una fecha específica
        
        Args:
            fecha: string, formato YYYY-MM-DD
            timezone: string opcional, ejemplo "Europe/London"
            force_refresh: Si True, fuerza llamada a la API
        """
        doc_id = f"date_{fecha}_{timezone or 'default'}"
        
        if not force_refresh:
            cached_data = self.fb.get_if_valid(self.COLLECTION_FIXTURES, doc_id)
            if cached_data:
                print(f"✓ Partidos de {fecha} obtenidos de Firebase")
                return cached_data
        
        print(f"⚡ Llamando a API externa: partidos {fecha}")
        url = f"{self.BASE_URL}/fixtures"
        params = {"date": fecha}
        if timezone:
            params["timezone"] = timezone
        
        response = requests.get(url, headers=self.headers, params=params)
        
        if response.status_code != 200:
            return {"results": 0, "response": []}
        
        data = response.json()
        
        # Partidos futuros: cache más largo
        self.fb.set_with_ttl(
            self.COLLECTION_FIXTURES, 
            doc_id, 
            data, 
            300  # 5 minutos
        )
        
        return data
    
    # ===== BÚSQUEDA DE EQUIPOS =====
    
    def search_team_by_name(
        self, 
        team_name: str,
        force_refresh: bool = False
    ) -> Dict[str, Any]:
        """Busca un equipo por nombre"""
        doc_id = f"team_search_{team_name.lower().strip()}"
        
        if not force_refresh:
            cached_data = self.fb.get_if_valid(self.COLLECTION_TEAM_STATS, doc_id)
            if cached_data:
                print(f"✓ Búsqueda de equipo '{team_name}' obtenida de Firebase")
                return cached_data
        
        print(f"⚡ Llamando a API externa: búsqueda equipo '{team_name}'")
        data = self.request_get("/teams", params={"search": team_name})
        
        self.fb.set_with_ttl(
            self.COLLECTION_TEAM_STATS, 
            doc_id, 
            data, 
            self.TTL_TEAM_STATS
        )
        
        return data
    
    # ===== ESTADÍSTICAS DE EQUIPO =====
    
    def get_team_statistics(
        self, 
        team_id: int, 
        league_id: int, 
        season: int,
        force_refresh: bool = False
    ) -> Dict[str, Any]:
        """Obtiene estadísticas de un equipo en una temporada específica"""
        doc_id = f"team_stats_{team_id}_{league_id}_{season}"
        
        if not force_refresh:
            cached_data = self.fb.get_if_valid(self.COLLECTION_TEAM_STATS, doc_id)
            if cached_data:
                print(f"✓ Estadísticas del equipo {team_id} obtenidas de Firebase")
                return cached_data
        
        print(f"⚡ Llamando a API externa: estadísticas equipo {team_id}")
        data = self.request_get(
            "/teams/statistics",
            params={
                "team": team_id,
                "league": league_id,
                "season": season
            }
        )
        
        self.fb.set_with_ttl(
            self.COLLECTION_TEAM_STATS, 
            doc_id, 
            data, 
            self.TTL_TEAM_STATS
        )
        
        return data
    
    # ===== TEMPORADAS DE EQUIPO =====
    
    def get_team_seasons(
        self, 
        team_id: int,
        force_refresh: bool = False
    ) -> Dict[str, Any]:
        """Obtiene temporadas disponibles para un equipo"""
        doc_id = f"seasons_{team_id}"
        
        if not force_refresh:
            cached_data = self.fb.get_if_valid(self.COLLECTION_TEAM_SEASONS, doc_id)
            if cached_data:
                print(f"✓ Temporadas del equipo {team_id} obtenidas de Firebase")
                return cached_data
        
        print(f"⚡ Llamando a API externa: temporadas equipo {team_id}")
        data = self.request_get("/teams/seasons", params={"team": team_id})
        
        self.fb.set_with_ttl(
            self.COLLECTION_TEAM_SEASONS, 
            doc_id, 
            data, 
            self.TTL_TEAM_SEASONS
        )
        
        return data
    
    # ===== MÉTODO GENÉRICO =====
    
    def request_get(
        self, 
        endpoint: str, 
        params: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Método genérico para hacer solicitudes GET a API-FOOTBALL"""
        url = f"{self.BASE_URL}{endpoint}"
        response = requests.get(url, headers=self.headers, params=params, timeout=10)
        return response.json()
    
    # ===== MÉTODOS DE UTILIDAD =====
    
    @staticmethod
    def normalize_event(event: Dict[str, Any]) -> Dict[str, Any]:
        """Normaliza un evento de la API"""
        time_data = event.get("time", {}) or {}
        team_data = event.get("team", {}) or {}
        player_data = event.get("player", {}) or {}
        
        # Extraer valores básicos
        minuto = time_data.get("elapsed")
        team_id = team_data.get("id")
        player_id = player_data.get("id")
        tipo = event.get("type")
        detalle = event.get("detail")
        
        # Crear clave única segura (convertir todo a strings o usar valores por defecto)
        # Esto previene errores de "unhashable type"
        key_parts = [
            str(minuto if minuto is not None else -1),
            str(team_id if team_id is not None else ""),
            str(player_id if player_id is not None else ""),
            str(tipo if tipo is not None else ""),
            str(detalle if detalle is not None else "")
        ]
        
        # Unir con separador para crear clave única
        unique_key = "|".join(key_parts)
        
        return {
            "minuto": minuto,
            "equipo": team_data.get("name"),
            "jugador": player_data.get("name"),
            "tipo": tipo,
            "detalle": detalle,
            "_key": unique_key  # Ahora es un string, no una tupla
        }
    

    def diff_new_events(
            self, 
            fixture_id: int, 
            new_events: List[Dict]
        ) -> List[Dict]:
        """
        Identifica eventos nuevos comparando con los guardados en Firebase
        
        Args:
            fixture_id: ID del partido
            new_events: Lista de eventos actuales (ya normalizados)
        
        Returns:
            Lista de eventos nuevos únicamente
        """
        doc_id = f"last_events_{fixture_id}"
        
        # Obtener eventos previos de Firebase
        prev_data = self.fb.get_if_valid(self.COLLECTION_EVENTS, doc_id)
        prev_events = prev_data if prev_data else []
        
        # Crear set de claves previas (ahora son strings)
        prev_keys = {e.get("_key") for e in prev_events if e.get("_key")}
        
        # Filtrar solo eventos nuevos
        new = [e for e in new_events if e.get("_key") and e.get("_key") not in prev_keys]
        
        # Si hay nuevos eventos, actualizar en Firebase
        if new:
            merged = prev_events + new
            self.fb.set_with_ttl(
                self.COLLECTION_EVENTS, 
                doc_id, 
                merged, 
                300  # 5 minutos
            )
        
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

    def get_live_fixtures_formatted(self, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Obtiene partidos en vivo YA FORMATEADOS
        
        OPTIMIZACIÓN: En lugar de que cada usuario formatee los datos,
        se formatean una vez y se guardan en Firebase.
        
        Returns:
            {"total": int, "matches": List[MatchInfo]}
        """
        # Colección separada para datos formateados
        COLLECTION_FORMATTED = "live_fixtures_formatted"
        doc_id = "current_formatted"
        
        # 1. Intentar obtener datos YA formateados de Firebase
        if not force_refresh:
            formatted_data = self.fb.get_if_valid(COLLECTION_FORMATTED, doc_id)
            if formatted_data:
                print(f"✓ Live fixtures formateados obtenidos de Firebase")
                return formatted_data
        
        # 2. Si no hay cache, obtener datos RAW y formatear
        raw_data = self.get_live_fixtures(force_refresh=force_refresh)
        
        if raw_data.get("results", 0) == 0:
            formatted = {"total": 0, "matches": []}
        else:
            # Formatear una sola vez
            matches = [self.format_match_info(match) for match in raw_data["response"]]
            formatted = {"total": len(matches), "matches": matches}
        
        # 3. Guardar datos formateados en Firebase (TTL 60s)
        self.fb.set_with_ttl(COLLECTION_FORMATTED, doc_id, formatted, 60)
        
        print(f"✓ {formatted['total']} partidos formateados y guardados en Firebase")
        
        return formatted