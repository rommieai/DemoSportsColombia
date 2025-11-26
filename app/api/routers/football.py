"""Endpoints para datos de fútbol en vivo"""
from fastapi import APIRouter, HTTPException, Query, Depends, BackgroundTasks
from fastapi.responses import StreamingResponse
from typing import Optional

from app.schemas.football import LiveMatchesBasicResponse
from app.core.cache import TTLCache
from app.schemas.football import (
    # Responses
    LiveMatchesResponse, MatchInfo, MatchEventsResponse,
    FixturesByDateResponse, LeaguesResponse, LineupResponse,
    CompleteMatchResponse, CommentaryResponse, AskResponse,
    TriviaResponse,
    # Requests
    AskRequest, TriviaRequest,
    # Basic models
    FixtureBasicInfo
)
from app.services.football_service import FootballAPIService
from app.services.commentary_service import CommentaryService
from app.services.trivia_service import TriviaService
from app.services.stream_service import StreamService
from app.core.config import get_settings
from app.core.cache import match_data_cache
from app.tasks import refresh_match_data


# ===== ROUTER Y DEPENDENCIES =====
router = APIRouter(prefix="/football", tags=["Football Live Data"])


def get_football_service() -> FootballAPIService:
    """Dependency: Servicio de API de fútbol"""
    settings = get_settings()
    api_key = getattr(settings, 'FOOTBALL_API_KEY', "0e88fe12ff5324e08d0dd7b35659829e")
    return FootballAPIService(api_key)


def get_commentary_service() -> CommentaryService:
    """Dependency: Servicio de comentarios"""
    return CommentaryService()


def get_trivia_service() -> TriviaService:
    """Dependency: Servicio de trivia"""
    return TriviaService()


def get_stream_service(
    football_service: FootballAPIService = Depends(get_football_service)
) -> StreamService:
    """Dependency: Servicio de streaming"""
    return StreamService(football_service)


# ===== ENDPOINTS: LIVE MATCHES =====

@router.get("/live-matches", response_model=LiveMatchesBasicResponse)
async def get_live_matches(service: FootballAPIService = Depends(get_football_service)):
    data = service.get_live_fixtures()
    if data.get("results", 0) == 0:
        return {"total": 0, "matches": []}
    matches = [service.format_match_info(match) for match in data["response"]]
    return {"total": len(matches), "matches": matches}


# ===== ENDPOINTS: FIXTURE SEARCH =====

@router.get("/fixtures-by-date", response_model=FixturesByDateResponse)
async def get_fixtures_by_date(
    fecha: str = Query(..., description="Fecha de los partidos en formato YYYY-MM-DD"),
    service: FootballAPIService = Depends(get_football_service)
):
    """
    Devuelve todos los partidos programados para una fecha específica.
    
    - **fecha**: Fecha de los partidos (YYYY-MM-DD)
    """
    data = service.get_fixtures_by_date(fecha)
    
    if data.get("results", 0) == 0:
        raise HTTPException(404, f"No hay partidos programados para la fecha {fecha}")
    
    resultados = []
    for match in data["response"]:
        resultados.append({
            "fixture_id": match["fixture"]["id"],
            "local": match["teams"]["home"]["name"],
            "visitante": match["teams"]["away"]["name"],
            "liga": match["league"]["name"],
            "fecha": match["fixture"]["date"],
            "estado": match["fixture"]["status"]["long"]
        })
    
    return {"total": len(resultados), "partidos": resultados}


@router.get("/fixture-by-date-teams", response_model=FixtureBasicInfo)
async def get_fixture_by_date_and_teams(
    fecha: str = Query(..., description="Fecha del partido (YYYY-MM-DD)"),
    local: str = Query(..., description="Nombre parcial del equipo local"),
    visitante: str = Query(..., description="Nombre parcial del equipo visitante"),
    service: FootballAPIService = Depends(get_football_service)
):
    """
    Busca un fixture por fecha y por los nombres de los equipos.
    
    - **fecha**: Fecha del partido (YYYY-MM-DD)
    - **local**: Nombre (parcial) del equipo local
    - **visitante**: Nombre (parcial) del equipo visitante
    """
    data = service.get_fixtures_by_date(fecha)
    
    if data.get("results", 0) == 0:
        raise HTTPException(404, f"No hay partidos programados para la fecha {fecha}")
    
    for match in data["response"]:
        home_name = match["teams"]["home"]["name"].lower()
        away_name = match["teams"]["away"]["name"].lower()
        
        if local.lower() in home_name and visitante.lower() in away_name:
            return {
                "fixture_id": match["fixture"]["id"],
                "local": match["teams"]["home"]["name"],
                "visitante": match["teams"]["away"]["name"],
                "liga": match["league"]["name"],
                "fecha": match["fixture"]["date"],
                "estado": match["fixture"]["status"]["long"],
                "minuto": match["fixture"]["status"]["elapsed"]
            }
    
    raise HTTPException(404, f"No se encontró un partido entre {local} y {visitante} en la fecha {fecha}")


@router.get("/find-fixture", response_model=FixtureBasicInfo)
async def find_fixture(
    local: str = Query(..., description="Nombre del equipo local"),
    visitante: str = Query(..., description="Nombre del equipo visitante"),
    liga: str = Query(..., description="Nombre de la liga"),
    service: FootballAPIService = Depends(get_football_service)
):
    """
    Busca el fixture_id de un partido en vivo por equipos y liga.
    
    - **local**: Nombre (parcial) del equipo local
    - **visitante**: Nombre (parcial) del equipo visitante
    - **liga**: Nombre (parcial) de la liga
    """
    data = service.get_live_fixtures()
    
    if data.get("results", 0) == 0:
        raise HTTPException(404, "No hay partidos en vivo")
    
    for match in data["response"]:
        home = match["teams"]["home"]["name"].lower()
        away = match["teams"]["away"]["name"].lower()
        league_name = match["league"]["name"].lower()
        
        if (local.lower() in home and 
            visitante.lower() in away and 
            liga.lower() in league_name):
            
            return {
                "fixture_id": match["fixture"]["id"],
                "local": match["teams"]["home"]["name"],
                "visitante": match["teams"]["away"]["name"],
                "liga": match["league"]["name"],
                "estado": match["fixture"]["status"]["long"],
                "minuto": match["fixture"]["status"]["elapsed"]
            }
    
    raise HTTPException(404, "No se encontró un partido con esos parámetros")


# ===== ENDPOINTS: MATCH DETAILS =====

@router.get("/match/{fixture_id}", response_model=MatchInfo)
async def get_match_detail(
    fixture_id: int,
    service: FootballAPIService = Depends(get_football_service)
):
    """
    Obtiene información detallada de un partido específico.
    
    - **fixture_id**: ID del partido
    - **Incluye**: Eventos, estadísticas, estado actual
    - **Caché**: Estadísticas cacheadas por 60 segundos
    """
    data = service.get_fixture_by_id(fixture_id)
    
    if data.get("results", 0) == 0:
        raise HTTPException(404, "No se encontró el partido")
    
    match = data["response"][0]
    fixture = match["fixture"]
    league = match["league"]
    teams = match["teams"]
    goals = match["goals"]
    status = fixture["status"]
    events = match.get("events", [])
    
    # Obtener estadísticas
    stats_data = service.get_fixture_statistics(fixture_id)
    estadisticas = {}
    for equipo_stats in stats_data:
        equipo = equipo_stats["team"]["name"]
        estadisticas[equipo] = {
            s["type"]: s["value"] for s in equipo_stats["statistics"]
        }
    
    # Procesar eventos
    eventos = [{
        "minuto": e["time"]["elapsed"],
        "equipo": e["team"]["name"],
        "jugador": e["player"]["name"] if e["player"] else None,
        "tipo": e["type"],
        "detalle": e["detail"]
    } for e in events]
    
    # Detectar nuevos eventos
    from app.core.cache import events_history
    nuevo_evento = events_history.has_new_events(fixture_id, eventos)
    if nuevo_evento:
        events_history.set_last_events(fixture_id, eventos)
    
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
        "minuto": status["elapsed"],
        "eventos": eventos,
        "nuevo_evento": nuevo_evento,
        "estadisticas": estadisticas
    }


@router.get("/match-complete/{fixture_id}", response_model=CompleteMatchResponse)
async def get_complete_match_info(
    fixture_id: int,
    service: FootballAPIService = Depends(get_football_service)
):
    """
    ENDPOINT TODO-EN-UNO: Obtiene TODA la información de un partido.
    
    - **fixture_id**: ID del partido
    - **Incluye**: Info básica, eventos, estadísticas, alineaciones
    
    ### Perfecto para:
    - Pantallas de partido completo
    - Reducir número de llamadas a la API
    """
    match_data = service.get_fixture_by_id(fixture_id)
    
    if match_data.get("results", 0) == 0:
        raise HTTPException(404, "No se encontró el partido")
    
    match = match_data["response"][0]
    fixture = match["fixture"]
    league = match["league"]
    teams = match["teams"]
    goals = match["goals"]
    status = fixture["status"]
    events = match.get("events", [])
    
    # Estadísticas
    stats_data = service.get_fixture_statistics(fixture_id)
    estadisticas = {}
    for equipo_stats in stats_data:
        equipo = equipo_stats["team"]["name"]
        estadisticas[equipo] = {
            s["type"]: s["value"] for s in equipo_stats["statistics"]
        }
    
    # Eventos
    eventos = [{
        "minuto": e["time"]["elapsed"],
        "equipo": e["team"]["name"],
        "jugador": e["player"]["name"] if e["player"] else None,
        "tipo": e["type"],
        "detalle": e["detail"]
    } for e in events]
    
    # Lineups
    lineups_data = service.get_fixture_lineups(fixture_id)
    lineups = []
    
    if lineups_data:
        for lineup in lineups_data:
            team = lineup.get("team", {})
            coach = lineup.get("coach", {})
            
            startXI = [
                {
                    "id": p.get("player", {}).get("id"),
                    "name": p.get("player", {}).get("name"),
                    "number": p.get("player", {}).get("number"),
                    "pos": p.get("player", {}).get("pos"),
                    "grid": p.get("player", {}).get("grid")
                }
                for p in lineup.get("startXI", [])
            ]
            
            substitutes = [
                {
                    "id": p.get("player", {}).get("id"),
                    "name": p.get("player", {}).get("name"),
                    "number": p.get("player", {}).get("number"),
                    "pos": p.get("player", {}).get("pos")
                }
                for p in lineup.get("substitutes", [])
            ]
            
            lineups.append({
                "team_name": team.get("name"),
                "formation": lineup.get("formation"),
                "coach_name": coach.get("name"),
                "startXI": startXI,
                "substitutes": substitutes
            })
    
    return {
        "fixture_id": fixture["id"],
        "fecha": fixture["date"],
        "liga": league["name"],
        "pais": league["country"],
        "equipos": {
            "local": teams["home"]["name"],
            "visitante": teams["away"]["name"],
            "local_logo": teams["home"].get("logo") or TEAM_LOGOS.get(teams["home"]["name"]),
            "visitante_logo": teams["away"].get("logo") or TEAM_LOGOS.get(teams["away"]["name"])
        },


        "marcador": {
            "local": goals["home"],
            "visitante": goals["away"]
        },
        "estado": status["long"],
        "minuto": status["elapsed"],
        "eventos": eventos,
        "estadisticas": estadisticas,
        "lineups": lineups,
        "lineups_disponibles": len(lineups) > 0
    }




# ===== ENDPOINTS: EVENTS =====

@router.get("/match-events/{fixture_id}", response_model=MatchEventsResponse)
async def get_match_events(
    fixture_id: int,
    service: FootballAPIService = Depends(get_football_service)
):
    """
    Obtiene un snapshot de todos los eventos actuales del partido.
    
    - **fixture_id**: ID del partido
    - **Uso**: Ideal para primera carga antes de conectarse al stream
    """
    from app.core.cache import events_cache, events_history
    
    # Intentar cache
    cached_events = events_cache.get(f"events:{fixture_id}")
    
    if cached_events is None:
        # Obtener desde API
        eventos_raw = service.get_fixture_events(fixture_id)
        
        if not eventos_raw:
            raise HTTPException(404, f"No se encontraron eventos para fixture {fixture_id}")
        
        cached_events = [service.normalize_event(e) for e in eventos_raw]
        cached_events.sort(key=lambda x: (x["minuto"] if x["minuto"] is not None else -1))
        
        # Guardar en cache
        events_cache.set(f"events:{fixture_id}", cached_events)
    
    # Actualizar historial
    events_history.set_last_events(fixture_id, cached_events)
    
    return {
        "fixture_id": fixture_id,
        "eventos": cached_events,
        "total": len(cached_events)
    }


@router.get("/stream-events/{fixture_id}")
async def stream_match_events(
    fixture_id: int,
    poll_sec: float = Query(default=10.0, ge=10.0, le=10.0),
    stream_service: StreamService = Depends(get_stream_service)
):
    """
    Stream en tiempo real de eventos del partido (Server-Sent Events).
    
    - **fixture_id**: ID del partido
    - **poll_sec**: Intervalo de polling (fijo en 10 segundos)
    - **Eventos**: ready, events, error
    """
    return StreamingResponse(
        stream_service.stream_match_events(fixture_id, poll_sec),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


# ===== ENDPOINTS: LEAGUES =====

@router.get("/leagues", response_model=LeaguesResponse)
async def get_leagues(
    service: FootballAPIService = Depends(get_football_service)
):
    """
    Obtiene todas las ligas disponibles en la API.
    
    - **Sin parámetros**: Retorna lista completa
    - **Uso**: Para mostrar catálogo de ligas disponibles
    """
    data = service.get_leagues()
    
    if data.get("results", 0) == 0:
        return {"total_ligas": 0, "ligas": []}
    
    ligas = []
    for league in data.get("response", []):
        l = league["league"]
        c = league["country"]
        ligas.append({
            "id": l["id"],
            "nombre": l["name"],
            "pais": c["name"],
            "tipo": l["type"],
            "temporada_actual": l.get("season"),
            "logo": l["logo"]
        })
    
    return {"total_ligas": len(ligas), "ligas": ligas}


@router.get("/find-league")
async def find_league(
    nombre: str = Query(..., description="Nombre de la liga a buscar"),
    service: FootballAPIService = Depends(get_football_service)
):
    """
    Busca una liga específica por nombre.
    
    - **nombre**: Nombre (parcial) de la liga
    - **Retorna**: Primera coincidencia encontrada
    """
    data = service.get_leagues()
    
    if data.get("results", 0) == 0:
        raise HTTPException(500, "No se pudieron obtener las ligas")
    
    for league in data["response"]:
        l = league["league"]
        c = league["country"]
        if nombre.lower() in l["name"].lower():
            return {
                "id": l["id"],
                "nombre": l["name"],
                "pais": c["name"],
                "tipo": l["type"],
                "temporada_actual": l.get("season"),
                "logo": l["logo"]
            }
    
    raise HTTPException(404, f"No se encontró una liga con el nombre '{nombre}'")


@router.get("/lineups/{fixture_id}", response_model=LineupResponse)
async def get_match_lineups(
    fixture_id: int,
    service: FootballAPIService = Depends(get_football_service)
):
    """
    Obtiene las alineaciones (lineups) de un partido.
    
    - **fixture_id**: ID del partido
    - **Incluye**: Titulares, suplentes, formación, entrenador
    """
    POSITION_MAP = {
        "G": "Portero",
        "D": "Defensa",
        "M": "Mediocampista",
        "F": "Delantero"
    }
    
    def map_position(pos_letter: str):
        if not pos_letter:
            return "Desconocido"
        return POSITION_MAP.get(pos_letter.upper(), "Desconocido")
    
    # Información del partido
    match_data = service.get_fixture_by_id(fixture_id)
    
    if match_data.get("results", 0) == 0:
        raise HTTPException(404, "No se encontró el partido")
    
    match = match_data["response"][0]
    teams = match["teams"]
    
    # Alineaciones
    lineups_data = service.get_fixture_lineups(fixture_id)
    
    if not lineups_data:
        raise HTTPException(
            404,
            "No hay alineaciones disponibles. "
            "Las alineaciones solo están disponibles cuando el partido ha comenzado "
            "o está próximo a comenzar."
        )
    
    lineups_processed = []
    total_players = 0
    
    for lineup in lineups_data:
        team = lineup.get("team", {})
        coach = lineup.get("coach", {})
        
        # Titulares
        startXI = []
        for player_data in lineup.get("startXI", []):
            player = player_data.get("player", {})
            pos_word = map_position(player.get("pos"))
            
            startXI.append({
                "id": player.get("id"),
                "name": player.get("name"),
                "number": player.get("number"),
                "pos": pos_word,
                "grid": player.get("grid"),
                "position": {
                    "x": player.get("x"),
                    "y": player.get("y")
                } if player.get("x") is not None and player.get("y") is not None else None
            })
        
        # Suplentes
        substitutes = []
        for player_data in lineup.get("substitutes", []):
            player = player_data.get("player", {})
            pos_word = map_position(player.get("pos"))
            
            substitutes.append({
                "id": player.get("id"),
                "name": player.get("name"),
                "number": player.get("number"),
                "pos": pos_word,
                "grid": player.get("grid"),
                "position": None
            })
        
        total_players += len(startXI) + len(substitutes)
        
        lineups_processed.append({
            "team_id": team.get("id"),
            "team_name": team.get("name"),
            "formation": lineup.get("formation"),
            "coach_id": coach.get("id"),
            "coach_name": coach.get("name"),
            "coach_photo": coach.get("photo"),
            "colors": lineup.get("colors", {}),
            "startXI": startXI,
            "substitutes": substitutes
        })
    
    return {
        "fixture_id": fixture_id,
        "equipos": {
            "local": teams["home"]["name"],
            "visitante": teams["away"]["name"]
        },
        "lineups": lineups_processed,
        "total_players": total_players
    }


# ===== ENDPOINTS: AI COMMENTARY =====

@router.post("/ask/{match_id}", response_model=AskResponse)
async def ask_commentator(
    match_id: int,
    req: AskRequest,
    commentary_service: CommentaryService = Depends(get_commentary_service)
):
    """Pregunta al comentarista IA sobre un partido específico."""
    
    # Intentar obtener datos del cache
    match_data = match_data_cache.get(match_id)
    
    if not match_data:
        # Forzar fetch inmediato
        await refresh_match_data(match_id)
        match_data = match_data_cache.get(match_id)
    
    if not match_data:
        raise HTTPException(404, "No se pudo obtener información del partido para responder la pregunta.")
    
    # Generar respuesta
    result = await commentary_service.answer_question(
        match_id=match_id,
        question=req.question,
        match_data=match_data
    )
    
    if "error" in result:
        raise HTTPException(500, result["error"])
    
    return result


@router.get("/commentary/{match_id}", response_model=CommentaryResponse)
async def get_match_commentary(
    match_id: int,
    background_tasks: BackgroundTasks,
    commentary_service: CommentaryService = Depends(get_commentary_service)
):
    """
    Genera un comentario corto y relevante sobre el partido.
    
    - **match_id**: ID del partido
    - **Cache**: 60 segundos
    - **Actualización**: Detecta cambios automáticamente
    """

    # Intentar obtener datos del cache
    current_data = match_data_cache.get(match_id)
    
    if not current_data:
        try:
            # Intentar refrescar datos desde la fuente externa
            await refresh_match_data(match_id)
            current_data = match_data_cache.get(match_id)
        except Exception as e:
            # Captura errores de conexión o fallos de la API externa
            raise HTTPException(
                503, 
                detail=f"No se pudo obtener información del partido {match_id} desde la API externa: {str(e)}"
            )
    
    if not current_data:
        # Datos no disponibles tras refresco
        raise HTTPException(
            404, 
            detail=f"No hay información disponible para el partido {match_id}. "
                   "Puede que el partido no exista o la API externa no tenga datos aún."
        )
    
    # Generar comentario
    try:
        result = await commentary_service.generate_commentary(match_id, current_data)
    except Exception as e:
        raise HTTPException(
            500,
            detail=f"Error generando comentario para el partido {match_id}: {str(e)}"
        )
    
    return result



# ===== ENDPOINTS: TRIVIA =====

@router.post("/trivia", response_model=TriviaResponse)
async def generate_trivia(
    payload: TriviaRequest,
    trivia_service: TriviaService = Depends(get_trivia_service)
):
    """
    Genera preguntas de trivia para dos equipos.
    
    - **team1**: Nombre del primer equipo
    - **team2**: Nombre del segundo equipo
    - **Preguntas**: 10 preguntas alternando equipos
    - **Cache**: 2 horas
    """
    result = await trivia_service.generate_trivia(
        team1=payload.team1,
        team2=payload.team2,
        num_questions=10
    )
    
    return result
two_hour_cache = TTLCache(ttl_seconds=7200)
team_seasons_cache = TTLCache(ttl_seconds=7200) 
@router.get("/team-stats/{team_name}")
async def get_team_statistics_by_name(
    team_name: str,
    season: Optional[int] = Query(None, description="Temporada específica (ej: 2024). Si no se especifica, muestra todas disponibles"),
    league_name: Optional[str] = Query(None, description="Nombre de la liga (opcional)"),
    service: FootballAPIService = Depends(get_football_service)
):
    """
    Obtiene estadísticas de un equipo por nombre.
    
    - **team_name**: Nombre del equipo (ej: "Barcelona")
    - **season**: Temporada opcional (ej: 2024). Si no se especifica, lista todas las disponibles
    - **league_name**: Nombre de la liga opcional (ej: "La Liga")
    
    Si no se especifica season, retorna info de temporadas disponibles.
    Si se especifica season, retorna estadísticas de esa temporada.
    """
    normalized = team_name.strip().lower()

    # 1. Buscar equipo por nombre
    team_search = service.search_team_by_name(normalized)

    if not team_search or team_search.get("results", 0) == 0:
        raise HTTPException(404, f"No se encontró el equipo '{team_name}'")

    team_info = team_search["response"][0]
    team_id = team_info["team"]["id"]
    team_real_name = team_info["team"]["name"]
    team_logo = team_info["team"].get("logo")
    team_country = team_info["team"].get("country")

    # 2. Obtener temporadas disponibles usando /teams/seasons
    try:
        seasons_response = service.request_get("/teams/seasons", params={"team": team_id})
        
        if not seasons_response or seasons_response.get("results", 0) == 0:
            raise HTTPException(
                404,
                f"No se encontraron temporadas disponibles para '{team_real_name}'"
            )
        
        available_seasons = seasons_response["response"]
        
    except Exception as e:
        raise HTTPException(
            500,
            f"Error al obtener temporadas: {str(e)}"
        )

    # Si no se especificó season, retornar info de temporadas disponibles
    if season is None:
        return {
            "equipo": {
                "id": team_id,
                "nombre": team_real_name,
                "pais": team_country,
                "logo": team_logo
            },
            "temporadas_disponibles": sorted(available_seasons, reverse=True),
            "mensaje": f"Especifica ?season=YYYY para obtener estadísticas. Ejemplo: ?season={available_seasons[-1] if available_seasons else 2024}"
        }

    # Verificar que la temporada solicitada esté disponible
    if season not in available_seasons:
        return {
            "equipo": {
                "id": team_id,
                "nombre": team_real_name,
                "pais": team_country,
                "logo": team_logo
            },
            "error": f"La temporada {season} no está disponible para {team_real_name}",
            "temporadas_disponibles": sorted(available_seasons, reverse=True),
            "sugerencia": f"Usa una de las temporadas disponibles, por ejemplo: ?season={available_seasons[-1]}"
        }

    # CACHE para temporada específica
    cache_key = f"team_stats:{normalized}:{season}:{league_name or 'default'}"
    cached = match_data_cache.get(cache_key)
    if cached:
        return {"cached": True, "data": cached}

    # 3. Buscar ligas donde jugó el equipo en esa temporada
    try:
        # Usar /teams con league y season para encontrar todas las ligas
        teams_in_season = service.request_get("/teams", params={
            "id": team_id,
            "season": season
        })
        
        if not teams_in_season or teams_in_season.get("results", 0) == 0:
            return {
                "equipo": {
                    "id": team_id,
                    "nombre": team_real_name,
                    "pais": team_country,
                    "logo": team_logo
                },
                "error": f"No hay datos de ligas para {team_real_name} en {season}",
                "temporadas_disponibles": sorted(available_seasons, reverse=True)
            }
        
        # Extraer todas las ligas de esa temporada
        available_leagues = []
        for entry in teams_in_season["response"]:
            league = entry.get("league", {})
            if league:
                available_leagues.append({
                    "league_id": league["id"],
                    "league_name": league["name"],
                    "country": league.get("country"),
                    "logo": league.get("logo")
                })
        
        if not available_leagues:
            return {
                "equipo": {
                    "id": team_id,
                    "nombre": team_real_name,
                    "logo": team_logo
                },
                "error": f"No se encontraron ligas para {team_real_name} en {season}",
                "temporadas_disponibles": sorted(available_seasons, reverse=True)
            }

    except Exception as e:
        raise HTTPException(500, f"Error al buscar ligas: {str(e)}")

    # 4. Seleccionar liga
    league_id = None
    selected_league = None
    
    if league_name:
        league_normalized = league_name.strip().lower()
        for league in available_leagues:
            if league_normalized in league["league_name"].lower():
                league_id = league["league_id"]
                selected_league = league
                break
        
        if league_id is None:
            available_names = [l["league_name"] for l in available_leagues]
            raise HTTPException(
                404,
                f"No se encontró la liga '{league_name}'. Ligas disponibles en {season}: {', '.join(available_names)}"
            )
    else:
        # Tomar la primera liga (normalmente la liga doméstica)
        selected_league = available_leagues[0]
        league_id = selected_league["league_id"]

    # 5. Obtener estadísticas
    try:
        stats_data = service.get_team_statistics(
            team_id=team_id,
            league_id=league_id,
            season=season
        )
        
        if not stats_data or stats_data.get("results", 0) == 0:
            return {
                "equipo": {
                    "id": team_id,
                    "nombre": team_real_name,
                    "logo": team_logo
                },
                "error": f"No hay estadísticas disponibles para {selected_league['league_name']} {season}",
                "ligas_disponibles": available_leagues
            }
        
        stats_raw = stats_data["response"]
        
    except Exception as e:
        raise HTTPException(500, f"Error al obtener estadísticas: {str(e)}")

    # 6. Formatear respuesta completa
    result = {
        "equipo": {
            "id": team_id,
            "nombre": stats_raw["team"]["name"],
            "logo": stats_raw["team"].get("logo")
        },
        "liga": {
            "id": stats_raw["league"]["id"],
            "nombre": stats_raw["league"]["name"],
            "pais": stats_raw["league"]["country"],
            "logo": stats_raw["league"].get("logo"),
            "bandera": stats_raw["league"].get("flag"),
            "temporada": stats_raw["league"]["season"]
        },
        "forma": stats_raw.get("form"),
        "partidos": stats_raw.get("fixtures", {}),
        "goles": stats_raw.get("goals", {}),
        "mayor_racha": stats_raw.get("biggest", {}),
        "porteria_cero": stats_raw.get("clean_sheet", {}),
        "fallo_anotar": stats_raw.get("failed_to_score", {}),
        "penales": stats_raw.get("penalty", {}),
        "alineaciones": stats_raw.get("lineups", []),
        "tarjetas": stats_raw.get("cards", {}),
        "otras_ligas_disponibles": [
            {
                "id": l["league_id"],
                "nombre": l["league_name"],
                "pais": l.get("country")
            } for l in available_leagues if l["league_id"] != league_id
        ]
    }

    # 7. Guardar en caché (2 horas)
    match_data_cache.set(cache_key, result, ttl=7200)

    return {
        "cached": False,
        "data": result
    }