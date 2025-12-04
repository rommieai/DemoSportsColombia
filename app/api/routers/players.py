"""Endpoints para información y estadísticas de jugadores - CON FIREBASE"""
from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Optional
from pydantic import BaseModel

from app.core.config import get_settings
from app.services.players_firebase_service import PlayersFirebaseService  # ✅ NUEVO
from app.services.players_business import PlayersBusinessService
from app.schemas.players import (
    PlayerDetailResponse,
    PlayerStatsFullResponse,
    PlayerSearchResult,
    SeasonsList,
    ErrorResponse
)

router = APIRouter(prefix="/players", tags=["Players Statistics"])


# ============== DEPENDENCIES ==============
def get_players_service() -> PlayersFirebaseService:
    """Inyección de dependencia: API Service con Firebase"""
    settings = get_settings()
    api_key = getattr(settings, 'FOOTBALL_API_KEY', "0e88fe12ff5324e08d0dd7b35659829e")
    return PlayersFirebaseService(api_key)  # ✅ Usa Firebase


def get_business_service(
    api_service: PlayersFirebaseService = Depends(get_players_service)
) -> PlayersBusinessService:
    """Inyección de dependencia: Business Service"""
    return PlayersBusinessService(api_service)


# ============== SIMPLE ENDPOINTS ==============
@router.get("/find")
async def find_player_simple(
    name: str = Query(..., min_length=3, description="Nombre o apellido del jugador"),
    force_refresh: bool = Query(False, description="Forzar actualización desde API"),
    service: PlayersFirebaseService = Depends(get_players_service)
):
    """
    🎯 BUSCA JUGADOR: Retorna ID y datos básicos.
    
    - **name**: Nombre o apellido (mínimo 3 caracteres)
    - **force_refresh**: Forzar actualización desde API externa
    - **Cache**: 1 hora en Firebase
    - **Ejemplo**: `/players/find?name=James Rodriguez`
    """
    data = service.search_players(name, page=1, force_refresh=force_refresh)
    results = data.get("results", 0)
    
    if results == 0:
        return {
            "encontrados": 0,
            "jugadores": [],
            "mensaje": f"No se encontraron jugadores con '{name}'"
        }
    
    players = data.get("response", [])
    
    jugadores_formateados = []
    for p in players[:10]:
        player_data = p.get("player", {})
        jugadores_formateados.append({
            "id": player_data.get("id"),
            "nombre_completo": player_data.get("name"),
            "nombre": player_data.get("firstname"),
            "apellido": player_data.get("lastname"),
            "edad": player_data.get("age"),
            "nacionalidad": player_data.get("nationality"),
            "foto": service.get_player_photo_url(player_data.get("id")),
            "altura": player_data.get("height"),
            "peso": player_data.get("weight")
        })
    
    return {
        "encontrados": len(jugadores_formateados),
        "total_en_api": results,
        "jugadores": jugadores_formateados
    }


@router.get("/complete/{player_id}")
async def get_player_complete_info(
    player_id: int,
    season: Optional[int] = Query(None, description="Temporada (YYYY). Si se omite, usa la más reciente."),
    force_refresh: bool = Query(False, description="Forzar actualización desde API"),
    business_service: PlayersBusinessService = Depends(get_business_service)
):
    """
    🎯 TODO-EN-UNO: Perfil + estadísticas.
    
    - **player_id**: ID del jugador (obtenido de `/players/find`)
    - **season**: Temporada opcional (ej: 2023)
    - **force_refresh**: Forzar actualización desde API
    - **Cache**: Varios niveles (perfiles: 7 días, stats: 1 hora)
    - **Ejemplo**: `/players/complete/1100?season=2023`
    """
    result = business_service.get_complete_player_info(player_id, season, force_refresh)
    
    if not result:
        raise HTTPException(404, f"Jugador con ID {player_id} no encontrado")
    
    return result


@router.get("/quick-stats")
async def get_quick_stats(
    name: str = Query(..., min_length=3, description="Nombre del jugador"),
    season: Optional[int] = Query(None, description="Temporada opcional"),
    nationality: Optional[str] = Query(None, alias="nacionalidad", description="Filtrar por nacionalidad"),
    force_refresh: bool = Query(False, description="Forzar actualización desde API"),
    service: PlayersFirebaseService = Depends(get_players_service),
    business_service: PlayersBusinessService = Depends(get_business_service)
):
    """
    ⚡ SUPER RÁPIDO: Busca y retorna estadísticas en un paso.
    
    OPTIMIZADO CON FIREBASE:
    - Primer nivel: Resultado completo pre-calculado (2 horas)
    - Segundo nivel: Búsquedas y estadísticas individuales (1 hora)
    - Usa AI fallback si no encuentra el jugador
    
    - **name**: Nombre del jugador
    - **season**: Temporada opcional
    - **nationality**: Filtrar por nacionalidad
    - **force_refresh**: Forzar actualización completa
    - **Ejemplos**: 
      - `/players/quick-stats?name=James&nationality=Colombia`
      - `/players/quick-stats?name=Messi&nacionalidad=Argentina`
    """
    # ✅ NIVEL 1: Intentar obtener resultado completo desde Firebase
    if not force_refresh:
        cached_result = service.get_quick_stats_from_cache(name, season, nationality)
        if cached_result:
            cached_result["_from_cache"] = True
            cached_result["_cache_level"] = "complete_result"
            return cached_result
    
    # ✅ NIVEL 2: Generar resultado (usa cache de búsquedas y stats)
    result = business_service.search_with_fallback(name, season, nationality, force_refresh)
    
    # ✅ Guardar resultado completo en Firebase
    service.get_quick_stats_cached(name, season, nationality, result)
    
    result["_from_cache"] = False
    result["_cache_level"] = "generated"
    
    return result


@router.get("/colombian")
async def find_colombian_players(
    name: Optional[str] = Query(None, min_length=3, description="Nombre del jugador colombiano"),
    force_refresh: bool = Query(False, description="Forzar actualización desde API"),
    service: PlayersFirebaseService = Depends(get_players_service)
):
    """
    🇨🇴 BÚSQUEDA ESPECIAL: Jugadores colombianos.
    
    - **Cache**: 1 hora en Firebase
    - **Ejemplo**: `/players/colombian?name=James`
    - `/players/colombian` - Lista jugadores conocidos
    """
    if name:
        data = service.search_players(name, page=1, force_refresh=force_refresh)
        players = data.get("response", [])
        
        colombian_players = []
        for p in players:
            player_data = p.get("player", {})
            if player_data.get("nationality", "").lower() == "colombia":
                colombian_players.append({
                    "id": player_data.get("id"),
                    "nombre": player_data.get("name"),
                    "edad": player_data.get("age"),
                    "foto": service.get_player_photo_url(player_data.get("id"))
                })
        
        return {"encontrados": len(colombian_players), "jugadores": colombian_players}
    else:
        colombianos_conocidos = [
            {"nombre": "James Rodríguez", "buscar": "James Rodriguez"},
            {"nombre": "Radamel Falcao", "buscar": "Falcao"},
            {"nombre": "Luis Díaz", "buscar": "Luis Diaz"},
            {"nombre": "Juan Cuadrado", "buscar": "Cuadrado"},
            {"nombre": "Yerry Mina", "buscar": "Yerry Mina"},
        ]
        
        return {
            "mensaje": "Jugadores colombianos conocidos",
            "jugadores_sugeridos": colombianos_conocidos,
            "ejemplo": "Usa: /players/find?name=James Rodriguez"
        }


# ============== STANDARD ENDPOINTS ==============
@router.get("/seasons", response_model=SeasonsList)
async def get_available_seasons(
    player_id: Optional[int] = Query(None, description="ID del jugador (opcional)"),
    force_refresh: bool = Query(False, description="Forzar actualización desde API"),
    service: PlayersFirebaseService = Depends(get_players_service)
):
    """
    Obtiene temporadas disponibles.
    
    - **Cache**: 1 día en Firebase
    - **Ejemplo**: `/players/seasons?player_id=276`
    """
    seasons = service.get_available_seasons(player_id, force_refresh)
    return {"seasons": sorted(seasons, reverse=True), "total": len(seasons)}


@router.get("/profile/{player_id}", response_model=PlayerDetailResponse)
async def get_player_profile(
    player_id: int,
    force_refresh: bool = Query(False, description="Forzar actualización desde API"),
    service: PlayersFirebaseService = Depends(get_players_service)
):
    """
    Obtiene perfil completo de un jugador.
    
    - **Cache**: 7 días en Firebase (perfil no cambia frecuentemente)
    - **Ejemplo**: `/players/profile/276`
    """
    profile = service.get_player_profile(player_id, force_refresh)
    
    if not profile:
        raise HTTPException(404, f"Jugador con ID {player_id} no encontrado")
    
    player_data = profile.get("player", {})
    
    return {
        "profile": player_data,
        "current_team": None,
        "position": None,
        "photo_url": service.get_player_photo_url(player_id)
    }


@router.get("/search")
async def search_players(
    name: str = Query(..., min_length=3, description="Apellido del jugador"),
    page: int = Query(1, ge=1, description="Número de página"),
    force_refresh: bool = Query(False, description="Forzar actualización desde API"),
    service: PlayersFirebaseService = Depends(get_players_service)
):
    """
    Busca jugadores por apellido.
    
    - **Paginación**: 250 resultados por página
    - **Cache**: 1 hora en Firebase
    - **Ejemplo**: `/players/search?name=Ronaldo`
    """
    data = service.search_players(name, page, force_refresh)
    
    results = data.get("results", 0)
    paging = data.get("paging", {})
    players = data.get("response", [])
    
    return {
        "total": results,
        "page": paging.get("current", 1),
        "total_pages": paging.get("total", 1),
        "players": [p.get("player", {}) for p in players]
    }


@router.get("/statistics/{player_id}", response_model=PlayerStatsFullResponse)
async def get_player_statistics(
    player_id: int,
    season: int = Query(..., description="Temporada (YYYY, ej: 2023)"),
    force_refresh: bool = Query(False, description="Forzar actualización desde API"),
    service: PlayersFirebaseService = Depends(get_players_service),
    business_service: PlayersBusinessService = Depends(get_business_service)
):
    """
    Obtiene estadísticas completas de un jugador.
    
    - **Cache**: 1 hora en Firebase
    - **Ejemplo**: `/players/statistics/276?season=2023`
    """
    data = service.get_player_statistics(
        player_id=player_id, 
        season=season,
        force_refresh=force_refresh
    )
    
    if data.get("results", 0) == 0:
        available_seasons = service.get_available_seasons(player_id, force_refresh=False)
        raise HTTPException(
            404,
            detail={
                "error": f"No hay estadísticas para jugador {player_id} en {season}",
                "available_seasons": sorted(available_seasons, reverse=True) if available_seasons else []
            }
        )
    
    response_data = data["response"][0]
    player_data = response_data.get("player", {})
    statistics = response_data.get("statistics", [])
    
    totals = business_service.calculate_totals(statistics)
    
    return {
        "player": player_data,
        "statistics": statistics,
        **totals
    }


@router.get("/statistics/team/{team_id}")
async def get_team_players_statistics(
    team_id: int,
    season: int = Query(..., description="Temporada (YYYY)"),
    page: int = Query(1, ge=1, description="Número de página"),
    force_refresh: bool = Query(False, description="Forzar actualización desde API"),
    service: PlayersFirebaseService = Depends(get_players_service)
):
    """
    Obtiene estadísticas de todos los jugadores de un equipo.
    
    - **Paginación**: 20 resultados por página
    - **Cache**: 1 hora en Firebase
    - **Ejemplo**: `/players/statistics/team/33?season=2023`
    """
    data = service.get_player_statistics(
        team_id=team_id, 
        season=season, 
        page=page,
        force_refresh=force_refresh
    )
    
    results = data.get("results", 0)
    paging = data.get("paging", {})
    
    if results == 0:
        raise HTTPException(404, f"No se encontraron jugadores para equipo {team_id} en {season}")
    
    return {
        "total": results,
        "page": paging.get("current", 1),
        "total_pages": paging.get("total", 1),
        "players": data.get("response", [])
    }


@router.get("/statistics/league/{league_id}")
async def get_league_players_statistics(
    league_id: int,
    season: int = Query(..., description="Temporada (YYYY)"),
    page: int = Query(1, ge=1, description="Número de página"),
    force_refresh: bool = Query(False, description="Forzar actualización desde API"),
    service: PlayersFirebaseService = Depends(get_players_service)
):
    """
    Obtiene estadísticas de jugadores de una liga.
    
    - **Cache**: 1 hora en Firebase
    - **Ejemplo**: `/players/statistics/league/39?season=2023&page=1`
    """
    data = service.get_player_statistics(
        league_id=league_id, 
        season=season, 
        page=page,
        force_refresh=force_refresh
    )
    
    results = data.get("results", 0)
    paging = data.get("paging", {})
    
    if results == 0:
        raise HTTPException(404, f"No se encontraron jugadores para liga {league_id} en {season}")
    
    return {
        "total": results,
        "page": paging.get("current", 1),
        "total_pages": paging.get("total", 1),
        "players": data.get("response", [])
    }


@router.get("/statistics/search")
async def search_player_statistics(
    name: str = Query(..., min_length=4, description="Nombre del jugador"),
    team_id: Optional[int] = Query(None, description="ID del equipo"),
    league_id: Optional[int] = Query(None, description="ID de la liga"),
    season: Optional[int] = Query(None, description="Temporada (YYYY)"),
    force_refresh: bool = Query(False, description="Forzar actualización desde API"),
    service: PlayersFirebaseService = Depends(get_players_service)
):
    """
    Busca estadísticas por nombre.
    
    - Requiere al menos `team_id` o `league_id`
    - **Cache**: 1 hora en Firebase
    - **Ejemplo**: `/players/statistics/search?name=Cavani&team_id=85`
    """
    if not team_id and not league_id:
        raise HTTPException(400, "Se requiere team_id o league_id")
    
    data = service.search_player_stats(name, team_id, league_id, season, force_refresh)
    
    results = data.get("results", 0)
    
    if results == 0:
        raise HTTPException(404, f"No se encontraron estadísticas para '{name}'")
    
    return {"total": results, "players": data.get("response", [])}


# ============== SQUADS ==============
@router.get("/squad/team/{team_id}")
async def get_team_squad(
    team_id: int,
    force_refresh: bool = Query(False, description="Forzar actualización desde API"),
    service: PlayersFirebaseService = Depends(get_players_service)
):
    """
    Obtiene el squad actual de un equipo.
    
    - **Cache**: 7 días en Firebase (plantillas cambian poco)
    - **Ejemplo**: `/players/squad/team/33`
    """
    data = service.get_team_squad(team_id, force_refresh)
    
    if data.get("results", 0) == 0:
        raise HTTPException(404, f"No se encontró squad para equipo {team_id}")
    
    return data.get("response", [])


@router.get("/squad/player/{player_id}")
async def get_player_squads(
    player_id: int,
    force_refresh: bool = Query(False, description="Forzar actualización desde API"),
    service: PlayersFirebaseService = Depends(get_players_service)
):
    """
    Obtiene todos los equipos de un jugador.
    
    - **Cache**: 7 días en Firebase
    - **Ejemplo**: `/players/squad/player/276`
    """
    data = service.get_player_teams(player_id, force_refresh)
    
    if data.get("results", 0) == 0:
        raise HTTPException(404, f"No se encontraron equipos para jugador {player_id}")
    
    return data.get("response", [])


@router.get("/teams/{player_id}")
async def get_player_teams_history(
    player_id: int,
    force_refresh: bool = Query(False, description="Forzar actualización desde API"),
    service: PlayersFirebaseService = Depends(get_players_service)
):
    """
    Obtiene historial completo de equipos del jugador.
    
    - **Cache**: 7 días en Firebase
    - **Ejemplo**: `/players/teams/276`
    """
    data = service.get_player_teams_history(player_id, force_refresh)
    
    if data.get("results", 0) == 0:
        raise HTTPException(404, f"No se encontró historial para jugador {player_id}")
    
    return data.get("response", [])


@router.get("/photo/{player_id}")
async def get_player_photo_url(
    player_id: int,
    service: PlayersFirebaseService = Depends(get_players_service)
):
    """
    Obtiene URL de la foto del jugador.
    
    - **Ejemplo**: `/players/photo/276`
    """
    return {
        "player_id": player_id,
        "photo_url": service.get_player_photo_url(player_id)
    }


# ============== AI FEATURES ==============
class PlayerBioRequest(BaseModel):
    name: str
    team: str


@router.post("/bio")
async def generate_player_bio(
    payload: PlayerBioRequest,
    business_service: PlayersBusinessService = Depends(get_business_service)
):
    """
    Genera biografía de un jugador con AI.
    
    - Usa caché interno de 1 día
    - **Ejemplo**: `POST /players/bio {"name": "James", "team": "São Paulo"}`
    """
    return business_service.generate_player_bio(payload.name, payload.team)


@router.get("/news")
async def get_player_news(
    name: str = Query(..., min_length=3, description="Nombre completo del jugador"),
    business_service: PlayersBusinessService = Depends(get_business_service)
):
    """
    Obtiene noticia reciente sobre un jugador (AI + Google News).
    
    - Usa búsqueda real en Google News
    - Genera resumen con IA
    - **Sin cache**: Siempre datos frescos
    - **Ejemplo**: `/players/news?name=James Rodriguez`
    """
    return business_service.generate_player_news(name)


# ============== MANTENIMIENTO (OPCIONAL) ==============
@router.post("/maintenance/cleanup")
async def cleanup_expired_cache(
    service: PlayersFirebaseService = Depends(get_players_service)
):
    """
    🔧 MANTENIMIENTO: Limpia datos expirados de Firebase.
    
    - Solo para uso administrativo
    - Libera espacio eliminando documentos expirados
    """
    results = service.cleanup_expired_data()
    total_cleaned = sum(results.values())
    
    return {
        "mensaje": "Limpieza completada",
        "total_eliminados": total_cleaned,
        "por_coleccion": results
    }