"""Endpoints para información y estadísticas de jugadores"""
from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Optional, List
from app.core.config import get_settings

import openai
from app.schemas.players import (
    PlayerDetailResponse,
    PlayerStatsFullResponse,
    PlayerSearchResult,
    SeasonsList,
    PlayerStatisticsResponse,
    SquadTeam,
    PlayerTeam,
    ErrorResponse
)
from app.services.players_service import PlayersAPIService
from app.core.config import get_settings

router = APIRouter(prefix="/players", tags=["Players Statistics"])

def get_players_service() -> PlayersAPIService:
    """Dependency para obtener el servicio de jugadores"""
    settings = get_settings()
    api_key = getattr(settings, 'FOOTBALL_API_KEY', "0e88fe12ff5324e08d0dd7b35659829e")
    return PlayersAPIService(api_key)

# ============== SEASONS ==============
@router.get("/seasons", response_model=SeasonsList)
async def get_available_seasons(
    player_id: Optional[int] = Query(None, description="ID del jugador (opcional)"),
    service: PlayersAPIService = Depends(get_players_service)
):
    """
    Obtiene todas las temporadas disponibles para estadísticas de jugadores.
    
    - **player_id**: ID del jugador (opcional). Si se omite, retorna todas las temporadas disponibles
    - **Caché**: 24 horas
    - **Uso recomendado**: 1 llamada por día
    
    ### Ejemplos:
    - `/players/seasons` - Todas las temporadas disponibles
    - `/players/seasons?player_id=276` - Temporadas para un jugador específico
    """
    seasons = service.get_available_seasons(player_id)
    
    return {
        "seasons": sorted(seasons, reverse=True),
        "total": len(seasons)
    }

# ============== PROFILE ==============
@router.get("/profile/{player_id}", response_model=PlayerDetailResponse)
async def get_player_profile(
    player_id: int,
    service: PlayersAPIService = Depends(get_players_service)
):
    """
    Obtiene el perfil completo de un jugador.
    
    - **player_id**: ID del jugador
    - **Incluye**: Datos personales, nacionalidad, altura, peso, foto
    - **Caché**: 7 días
    
    ### Ejemplo:
    - `/players/profile/276` - Perfil de Neymar
    """
    profile = service.get_player_profile(player_id)
    
    if not profile:
        raise HTTPException(404, f"Jugador con ID {player_id} no encontrado")
    

    player_data = profile.get("player", {})
    

    current_team = None
    position = None
    
    return {
        "profile": player_data,
        "current_team": current_team,
        "position": position,
        "photo_url": service.get_player_photo_url(player_id)
    }

@router.get("/news")
async def get_player_news(
    name: str = Query(..., min_length=3, description="Nombre completo del jugador"),
):
    """
    Obtiene una noticia o dato curioso reciente sobre un jugador de fútbol.
    
    - **name**: Nombre completo del jugador
    - **Respuesta**: Un párrafo muy corto con un dato interesante reciente
    """
    settings = get_settings()
    openai.api_key = settings.OPENAI_API_KEY

    prompt = (
        f"Escribe un párrafo muy breve sobre una noticia o dato curioso reciente "
        f"del jugador de fútbol {name}. Manténlo en máximo 3-4 líneas, estilo informativo y conciso."
    )

    try:
        response = openai.chat.completions.create(
            model=settings.OPENAI_MODEL_ID,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100,
            temperature=0.7
        )
        content = response.choices[0].message.content.strip()
        return {"player": name, "news": content}
    except Exception as e:
        return {"error": "No se pudo generar la noticia", "detail": str(e)}
@router.get("/search")
async def search_players(
    name: str = Query(..., min_length=3, description="Apellido del jugador (mínimo 3 caracteres)"),
    page: int = Query(1, ge=1, description="Número de página (250 resultados por página)"),
    service: PlayersAPIService = Depends(get_players_service)
):
    """
    Busca jugadores por apellido.
    
    - **name**: Apellido del jugador (mínimo 3 caracteres)
    - **page**: Número de página
    - **Paginación**: 250 resultados por página
    - **Caché**: 1 hora
    
    ### Ejemplos:
    - `/players/search?name=Ronaldo`
    - `/players/search?name=Messi&page=1`
    """
    data = service.search_players(name, page)
    
    results = data.get("results", 0)
    paging = data.get("paging", {})
    players = data.get("response", [])
    
    return {
        "total": results,
        "page": paging.get("current", 1),
        "total_pages": paging.get("total", 1),
        "players": [p.get("player", {}) for p in players]
    }

# ============== STATISTICS ==============
@router.get("/statistics/{player_id}", response_model=PlayerStatsFullResponse)
async def get_player_statistics(
    player_id: int,
    season: int = Query(..., description="Temporada (YYYY, ej: 2023)"),
    service: PlayersAPIService = Depends(get_players_service)
):
    """
    Obtiene estadísticas completas de un jugador en una temporada.
    
    - **player_id**: ID del jugador
    - **season**: Temporada (formato YYYY)
    - **Incluye**: Goles, asistencias, partidos, minutos, rating, etc.
    - **Caché**: 1 hora
    
    ### Ejemplo:
    - `/players/statistics/276?season=2023` - Estadísticas de Neymar en 2023
    """
    data = service.get_player_statistics(player_id=player_id, season=season)
    
    if data.get("results", 0) == 0:
        # Obtener temporadas disponibles para sugerencias
        available_seasons = service.get_available_seasons(player_id)
        raise HTTPException(
            404, 
            detail={
                "error": f"No se encontraron estadísticas para el jugador {player_id} en la temporada {season}",
                "available_seasons": sorted(available_seasons, reverse=True) if available_seasons else []
            }
        )
    
    response_data = data["response"][0]
    player_data = response_data.get("player", {})
    statistics = response_data.get("statistics", [])
    
    # Calcular totales
    totals = service.calculate_totals(statistics)
    
    return {
        "player": player_data,
        "statistics": statistics,
        **totals
    }

@router.get("/statistics/team/{team_id}")
async def get_team_players_statistics(
    team_id: int,
    season: int = Query(..., description="Temporada (YYYY)"),
    page: int = Query(1, ge=1, description="Número de página (20 resultados por página)"),
    service: PlayersAPIService = Depends(get_players_service)
):
    """
    Obtiene estadísticas de todos los jugadores de un equipo en una temporada.
    
    - **team_id**: ID del equipo
    - **season**: Temporada (formato YYYY)
    - **page**: Número de página
    - **Paginación**: 20 resultados por página
    - **Caché**: 1 hora
    
    ### Ejemplo:
    - `/players/statistics/team/33?season=2023` - Jugadores del Manchester United en 2023
    """
    data = service.get_player_statistics(team_id=team_id, season=season, page=page)
    
    results = data.get("results", 0)
    paging = data.get("paging", {})
    
    if results == 0:
        raise HTTPException(404, f"No se encontraron jugadores para el equipo {team_id} en la temporada {season}")
    
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
    page: int = Query(1, ge=1, description="Número de página (20 resultados por página)"),
    service: PlayersAPIService = Depends(get_players_service)
):
    """
    Obtiene estadísticas de jugadores de una liga en una temporada.
    
    - **league_id**: ID de la liga
    - **season**: Temporada (formato YYYY)
    - **page**: Número de página
    - **Paginación**: 20 resultados por página
    - **Caché**: 1 hora
    
    ### Ejemplo:
    - `/players/statistics/league/39?season=2023&page=1` - Premier League 2023
    """
    data = service.get_player_statistics(league_id=league_id, season=season, page=page)
    
    results = data.get("results", 0)
    paging = data.get("paging", {})
    
    if results == 0:
        raise HTTPException(404, f"No se encontraron jugadores para la liga {league_id} en la temporada {season}")
    
    return {
        "total": results,
        "page": paging.get("current", 1),
        "total_pages": paging.get("total", 1),
        "players": data.get("response", [])
    }

@router.get("/statistics/search")
async def search_player_statistics(
    name: str = Query(..., min_length=4, description="Nombre del jugador (mínimo 4 caracteres)"),
    team_id: Optional[int] = Query(None, description="ID del equipo"),
    league_id: Optional[int] = Query(None, description="ID de la liga"),
    season: Optional[int] = Query(None, description="Temporada (YYYY)"),
    service: PlayersAPIService = Depends(get_players_service)
):
    """
    Busca estadísticas de jugadores por nombre.
    
    - **name**: Nombre del jugador (mínimo 4 caracteres)
    - **team_id**: Filtrar por equipo (opcional)
    - **league_id**: Filtrar por liga (opcional)
    - **season**: Filtrar por temporada (opcional)
    - **Requiere**: Al menos team_id o league_id
    - **Caché**: 1 hora
    
    ### Ejemplos:
    - `/players/statistics/search?name=Cavani&team_id=85`
    - `/players/statistics/search?name=Cavani&league_id=61&season=2023`
    """
    if not team_id and not league_id:
        raise HTTPException(
            400, 
            "Se requiere al menos team_id o league_id para buscar estadísticas"
        )
    
    data = service.search_player_stats(name, team_id, league_id, season)
    
    results = data.get("results", 0)
    
    if results == 0:
        raise HTTPException(404, f"No se encontraron estadísticas para jugadores con nombre '{name}'")
    
    return {
        "total": results,
        "players": data.get("response", [])
    }

# ============== SQUADS ==============
@router.get("/squad/team/{team_id}")
async def get_team_squad(
    team_id: int,
    service: PlayersAPIService = Depends(get_players_service)
):
    """
    Obtiene el squad actual (plantilla) de un equipo.
    
    - **team_id**: ID del equipo
    - **Incluye**: Lista completa de jugadores con número, posición y foto
    - **Caché**: 7 días
    
    ### Ejemplo:
    - `/players/squad/team/33` - Squad del Manchester United
    """
    data = service.get_team_squad(team_id)
    
    if data.get("results", 0) == 0:
        raise HTTPException(404, f"No se encontró información del squad para el equipo {team_id}")
    
    return data.get("response", [])

@router.get("/squad/player/{player_id}")
async def get_player_squads(
    player_id: int,
    service: PlayersAPIService = Depends(get_players_service)
):
    """
    Obtiene todos los equipos asociados con un jugador.
    
    - **player_id**: ID del jugador
    - **Incluye**: Lista de equipos donde ha jugado
    - **Caché**: 7 días
    
    ### Ejemplo:
    - `/players/squad/player/276` - Equipos de Neymar
    """
    data = service.get_player_teams(player_id)
    
    if data.get("results", 0) == 0:
        raise HTTPException(404, f"No se encontraron equipos para el jugador {player_id}")
    
    return data.get("response", [])

# ============== TEAMS HISTORY ==============
@router.get("/teams/{player_id}")
async def get_player_teams_history(
    player_id: int,
    service: PlayersAPIService = Depends(get_players_service)
):
    """
    Obtiene el historial completo de equipos y temporadas del jugador.
    
    - **player_id**: ID del jugador
    - **Incluye**: Equipos, temporadas de inicio y fin
    - **Caché**: 7 días
    
    ### Ejemplo:
    - `/players/teams/276` - Historial de equipos de Neymar
    """
    data = service.get_player_teams_history(player_id)
    
    if data.get("results", 0) == 0:
        raise HTTPException(404, f"No se encontró historial de equipos para el jugador {player_id}")
    
    return data.get("response", [])

# ============== UTILITY ==============
@router.get("/photo/{player_id}")
async def get_player_photo_url(
    player_id: int,
    service: PlayersAPIService = Depends(get_players_service)
):
    """
    Obtiene la URL de la foto del jugador.
    
    - **player_id**: ID del jugador
    - **Retorna**: URL directa a la imagen
    
    ### Ejemplo:
    - `/players/photo/276` - Foto de Neymar
    """
    photo_url = service.get_player_photo_url(player_id)
    
    return {
        "player_id": player_id,
        "photo_url": photo_url
    }

# ============== ENDPOINTS SIMPLIFICADOS (AGREGAR AL FINAL DEL ARCHIVO) ==============

@router.get("/find")
async def find_player_simple(
    name: str = Query(..., min_length=3, description="Nombre o apellido del jugador"),
    service: PlayersAPIService = Depends(get_players_service)
):
    """
    🎯 ENDPOINT SIMPLIFICADO: Busca un jugador y retorna su ID y datos básicos.
    
    **Paso 1**: Usa este endpoint para encontrar el ID del jugador
    
    - **name**: Nombre o apellido del jugador (mínimo 3 caracteres)
    - **Retorna**: Lista de jugadores encontrados con sus IDs
    
    ### Ejemplos:
    - `/players/find?name=James Rodriguez`
    - `/players/find?name=Falcao`
    - `/players/find?name=Diaz`
    
    ### Respuesta incluye:
    - ID del jugador (usa este ID en otros endpoints)
    - Nombre completo
    - Edad, nacionalidad
    - URL de la foto
    """
    data = service.search_players(name, page=1)
    
    results = data.get("results", 0)
    
    if results == 0:
        return {
            "encontrados": 0,
            "jugadores": [],
            "mensaje": f"No se encontraron jugadores con el nombre '{name}'. Intenta con un apellido o nombre diferente."
        }
    
    players = data.get("response", [])
    
    # Formatear respuesta simple
    jugadores_formateados = []
    for p in players[:10]:  # Limitar a 10 primeros resultados
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
        "jugadores": jugadores_formateados,
        "mensaje": f"Se encontraron {results} jugadores. Mostrando los primeros {len(jugadores_formateados)}."
    }


@router.get("/complete/{player_id}")
async def get_player_complete_info(
    player_id: int,
    season: Optional[int] = Query(None, description="Temporada específica (YYYY). Si se omite, usa la más reciente."),
    service: PlayersAPIService = Depends(get_players_service)
):
    """
    🎯 ENDPOINT TODO-EN-UNO: Obtiene perfil + estadísticas de un jugador.
    
    **Paso 2**: Después de obtener el ID con /players/find, usa este endpoint
    
    - **player_id**: ID del jugador (obtenido de /players/find)
    - **season**: Temporada opcional (ej: 2023). Si no se especifica, usa la más reciente
    
    ### Ejemplos:
    - `/players/complete/1100` - Información completa de Mbappé (temporada más reciente)
    - `/players/complete/1100?season=2023` - Mbappé en 2023
    - `/players/complete/276?season=2022` - Neymar en 2022
    
    ### Respuesta incluye:
    - Perfil completo del jugador
    - Estadísticas de la temporada
    - Totales (goles, asistencias, partidos)
    - Lista de temporadas disponibles
    """
    # 1. Obtener perfil
    profile = service.get_player_profile(player_id)
    
    if not profile:
        raise HTTPException(404, f"Jugador con ID {player_id} no encontrado")
    
    player_data = profile.get("player", {})
    
    # 2. Obtener temporadas disponibles
    available_seasons = service.get_available_seasons(player_id)
    
    if not available_seasons:
        return {
            "perfil": player_data,
            "foto": service.get_player_photo_url(player_id),
            "estadisticas": None,
            "mensaje": "No hay estadísticas disponibles para este jugador",
            "temporadas_disponibles": []
        }
    
    # 3. Determinar temporada a usar
    if season is None:
        season = max(available_seasons)  # Usar la más reciente
    
    # 4. Obtener estadísticas
    stats_data = service.get_player_statistics(player_id=player_id, season=season)
    
    if stats_data.get("results", 0) == 0:
        return {
            "perfil": player_data,
            "foto": service.get_player_photo_url(player_id),
            "estadisticas": None,
            "mensaje": f"No hay estadísticas para la temporada {season}",
            "temporadas_disponibles": sorted(available_seasons, reverse=True),
            "temporada_solicitada": season
        }
    
    response_data = stats_data["response"][0]
    statistics = response_data.get("statistics", [])
    
    # 5. Calcular totales
    totals = service.calculate_totals(statistics)
    
    # 6. Formatear respuesta completa
    return {
        "perfil": {
            "id": player_data.get("id"),
            "nombre": player_data.get("name"),
            "edad": player_data.get("age"),
            "nacionalidad": player_data.get("nationality"),
            "altura": player_data.get("height"),
            "peso": player_data.get("weight"),
            "foto": service.get_player_photo_url(player_id)
        },
        "temporada": season,
        "estadisticas_detalladas": statistics,
        "resumen": {
            "goles": totals["total_goals"],
            "asistencias": totals["total_assists"],
            "partidos_jugados": totals["total_matches"],
            "minutos_jugados": totals["total_minutes"],
            "rating_promedio": totals["average_rating"],
            "tarjetas_amarillas": totals["total_yellow_cards"],
            "tarjetas_rojas": totals["total_red_cards"]
        },
        "temporadas_disponibles": sorted(available_seasons, reverse=True)
    }


@router.get("/colombian")
async def find_colombian_players(
    name: Optional[str] = Query(None, min_length=3, description="Nombre del jugador colombiano (opcional)"),
    service: PlayersAPIService = Depends(get_players_service)
):
    """
    🇨🇴 BÚSQUEDA ESPECIAL: Encuentra jugadores colombianos.
    
    - **name**: Nombre del jugador (opcional). Si no se especifica, muestra jugadores colombianos populares
    
    ### Ejemplos:
    - `/players/colombian?name=James`
    - `/players/colombian?name=Falcao`
    - `/players/colombian?name=Diaz`
    - `/players/colombian` - Lista jugadores colombianos conocidos
    
    ### Jugadores colombianos conocidos:
    - James Rodríguez
    - Radamel Falcao
    - Luis Díaz
    - Juan Cuadrado
    - Yerry Mina
    - Dávinson Sánchez
    """
    if name:
        # Buscar por nombre
        data = service.search_players(name, page=1)
        players = data.get("response", [])
        
        # Filtrar solo colombianos
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
        
        return {
            "encontrados": len(colombian_players),
            "jugadores": colombian_players
        }
    else:
        # Lista de IDs conocidos de jugadores colombianos
        colombianos_conocidos = [
            {"nombre": "James Rodríguez", "buscar": "James Rodriguez"},
            {"nombre": "Radamel Falcao", "buscar": "Falcao"},
            {"nombre": "Luis Díaz", "buscar": "Luis Diaz"},
            {"nombre": "Juan Cuadrado", "buscar": "Cuadrado"},
            {"nombre": "Yerry Mina", "buscar": "Yerry Mina"},
            {"nombre": "Dávinson Sánchez", "buscar": "Davinson Sanchez"},
            {"nombre": "Duván Zapata", "buscar": "Duvan Zapata"},
            {"nombre": "Jhon Arias", "buscar": "Jhon Arias"}
        ]
        
        return {
            "mensaje": "Jugadores colombianos conocidos. Usa /players/find?name={nombre} para buscarlos",
            "jugadores_sugeridos": colombianos_conocidos,
            "ejemplo": "Usa: /players/find?name=James Rodriguez"
        }


@router.get("/quick-stats")
async def get_quick_stats(
    name: str = Query(..., min_length=3, description="Nombre del jugador"),
    season: Optional[int] = Query(None, description="Temporada (opcional, usa la más reciente si se omite)"),
    service: PlayersAPIService = Depends(get_players_service)
):
    """
    ⚡ SUPER RÁPIDO: Busca jugador y retorna estadísticas en un solo paso.
    
    Este endpoint hace TODO automáticamente:
    1. Busca el jugador por nombre
    2. Obtiene sus estadísticas
    3. Retorna resumen simple
    
    - **name**: Nombre del jugador
    - **season**: Temporada opcional (usa la más reciente si se omite)
    
    ### Ejemplos:
    - `/players/quick-stats?name=Mbappe`
    - `/players/quick-stats?name=Haaland&season=2023`
    - `/players/quick-stats?name=James Rodriguez&season=2022`
    
    ### Caso de uso:
    Cuando no conoces el ID y quieres estadísticas rápidas
    """
    # 1. Buscar jugador
    search_data = service.search_players(name, page=1)
    
    if search_data.get("results", 0) == 0:
        raise HTTPException(404, f"No se encontró ningún jugador con el nombre '{name}'")
    
    # Tomar el primer resultado
    first_player = search_data["response"][0]
    player_data = first_player.get("player", {})
    player_id = player_data.get("id")
    
    # 2. Obtener temporadas disponibles
    available_seasons = service.get_available_seasons(player_id)
    
    if not available_seasons:
        return {
            "jugador": player_data,
            "mensaje": "No hay estadísticas disponibles para este jugador"
        }
    
    # 3. Determinar temporada
    if season is None:
        season = max(available_seasons)
    
    # 4. Obtener estadísticas
    stats_data = service.get_player_statistics(player_id=player_id, season=season)
    
    if stats_data.get("results", 0) == 0:
        return {
            "jugador": player_data,
            "mensaje": f"No hay estadísticas para la temporada {season}",
            "temporadas_disponibles": sorted(available_seasons, reverse=True)
        }
    
    response_data = stats_data["response"][0]
    statistics = response_data.get("statistics", [])
    totals = service.calculate_totals(statistics)
    
    # 5. Respuesta ultra-simple
    return {
        "jugador": {
            "id": player_id,
            "nombre": player_data.get("name"),
            "nacionalidad": player_data.get("nationality"),
            "edad": player_data.get("age"),
            "foto": service.get_player_photo_url(player_id)
        },
        "temporada": season,
        "goles": totals["total_goals"],
        "asistencias": totals["total_assists"],
        "partidos": totals["total_matches"],
        "minutos": totals["total_minutes"],
        "rating": totals["average_rating"],
        "equipos": [
            {
                "nombre": stat.get("team", {}).get("name"),
                "liga": stat.get("league", {}).get("name")
            }
            for stat in statistics
        ]
    }