"""Endpoints actualizados para usar Firebase en lugar de caché en memoria"""
from fastapi import APIRouter, HTTPException, Query, Depends, BackgroundTasks
from fastapi.responses import StreamingResponse
from typing import Optional
from app.services.colorExtractionService import get_team_colors_from_logo
from app.tasks import get_both_teams_stats_cached  # Importar la función batch
from app.services.mockStreamService import mockStreamService
from app.schemas.football import LiveMatchesBasicResponse
from app.schemas.football import (
    LiveMatchesResponse, MatchInfo, MatchEventsResponse,
    FixturesByDateResponse, LeaguesResponse, LineupResponse,
    CompleteMatchResponse, CommentaryResponse, AskResponse,
    TriviaResponse, AskRequest, TriviaRequest, FixtureBasicInfo
)
from app.services.football_firebase_service import FootballFirebaseService
from app.services.commentary_service import CommentaryService
from app.services.trivia_service import TriviaService
from app.services.stream_service import StreamService
from app.core.config import get_settings
from app.tasks import refresh_match_data, get_match_data_from_firebase

# ===== ROUTER Y DEPENDENCIES =====
router = APIRouter(prefix="/football", tags=["Football Live Data"])


def get_football_service() -> FootballFirebaseService:
    """Dependency: Servicio de API de fútbol con Firebase"""
    settings = get_settings()
    api_key = getattr(settings, 'FOOTBALL_API_KEY', "0e88fe12ff5324e08d0dd7b35659829e")
    return FootballFirebaseService(api_key)


def get_commentary_service() -> CommentaryService:
    """Dependency: Servicio de comentarios"""
    return CommentaryService()


def get_trivia_service() -> TriviaService:
    """Dependency: Servicio de trivia"""
    return TriviaService()


def get_stream_service(
    football_service: FootballFirebaseService = Depends(get_football_service)
) -> StreamService:
    """Dependency: Servicio de streaming"""
    return StreamService(football_service)


# ===== ENDPOINTS: LIVE MATCHES =====

@router.get("/live-matches", response_model=LiveMatchesBasicResponse)
async def get_live_matches(
    force_refresh: bool = Query(False, description="Forzar actualización desde API"),
    service: FootballFirebaseService = Depends(get_football_service)
):
    """
    Obtiene todos los partidos en vivo (OPTIMIZADO)
    
    MEJORA: Datos pre-formateados en Firebase para evitar procesamiento repetido
    
    - **force_refresh**: Si True, fuerza actualización desde API externa
    - **Cache doble**: 
        - Datos RAW: 60s
        - Datos formateados: 60s
    - **Beneficio**: 100 usuarios = 1 formateo, no 100 formateos
    """
    # Obtener datos YA formateados
    return service.get_live_fixtures_formatted(force_refresh=force_refresh)
    

# ===== ENDPOINTS: FIXTURE SEARCH =====

@router.get("/fixtures-by-date", response_model=FixturesByDateResponse)
async def get_fixtures_by_date(
    fecha: str = Query(..., description="Fecha de los partidos en formato YYYY-MM-DD"),
    force_refresh: bool = Query(False, description="Forzar actualización desde API"),
    service: FootballFirebaseService = Depends(get_football_service)
):
    """
    Devuelve todos los partidos programados para una fecha específica.
    
    - **fecha**: Fecha de los partidos (YYYY-MM-DD)
    - **force_refresh**: Forzar actualización desde API
    - **Cache**: 5 minutos en Firebase
    """
    data = service.get_fixtures_by_date(fecha, force_refresh=force_refresh)
    
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


@router.get("/match-complete/{fixture_id}", response_model=CompleteMatchResponse)
async def get_complete_match_info(
    fixture_id: int,
    force_refresh: bool = Query(False, description="Forzar actualización desde API"),
    extract_colors: bool = Query(True, description="Extraer colores de logos (puede ser más lento)"),
    service: FootballFirebaseService = Depends(get_football_service)
):
    """
    ENDPOINT TODO-EN-UNO OPTIMIZADO: Obtiene TODA la información de un partido.
    
    NUEVO: Incluye colores dominantes extraídos de los logos
    
    Args:
        fixture_id: ID del partido
        force_refresh: Forzar actualización desde API externa
        extract_colors: Si False, no extrae colores (más rápido)
    """
    # 1️⃣ OBTENER DATOS COMPLETOS DEL PARTIDO
    match_data = await refresh_match_data(fixture_id, force=force_refresh)
    
    if not match_data:
        raise HTTPException(404, "No se encontró el partido")
    
    # 2️⃣ EXTRAER DATOS BÁSICOS
    match = match_data["fixture"]
    fixture = match["fixture"]
    league = match["league"]
    teams = match["teams"]
    goals = match["goals"]
    status = fixture["status"]
    
    # IDs necesarios para estadísticas de temporada
    league_id = league["id"]
    season = int(fixture["date"][:4])
    home_team_id = teams["home"]["id"]
    away_team_id = teams["away"]["id"]
    
    # 🎨 EXTRAER COLORES DE LOGOS (NUEVO)
    home_logo = teams["home"].get("logo")
    away_logo = teams["away"].get("logo")
    
    home_colors = {"primary": "#1E40AF", "secondary": "#DC2626"}  # Default
    away_colors = {"primary": "#059669", "secondary": "#F59E0B"}  # Default
    
    if extract_colors:
        try:
            if home_logo:
                home_colors = get_team_colors_from_logo(home_logo)
            if away_logo:
                away_colors = get_team_colors_from_logo(away_logo)
        except Exception as e:
            print(f"Error extrayendo colores: {str(e)}")
            # Continuar con colores por defecto
    
    # 3️⃣ PROCESAR EVENTOS
    raw_events = match_data.get("events", [])
    eventos = []
    
    for e in raw_events:
        if isinstance(e, dict) and "minuto" in e:
            eventos.append({
                "minuto": e.get("minuto"),
                "equipo": e.get("equipo"),
                "jugador": e.get("jugador"),
                "tipo": e.get("tipo"),
                "detalle": e.get("detalle")
            })
        else:
            eventos.append({
                "minuto": e.get("time", {}).get("elapsed"),
                "equipo": e.get("team", {}).get("name"),
                "jugador": e.get("player", {}).get("name") if e.get("player") else None,
                "tipo": e.get("type"),
                "detalle": e.get("detail")
            })
    
    # 4️⃣ PROCESAR ESTADÍSTICAS DEL PARTIDO
    stats_data = match_data.get("statistics", [])
    estadisticas = {}
    
    for equipo_stats in stats_data:
        equipo = equipo_stats["team"]["name"]
        estadisticas[equipo] = {
            s["type"]: s["value"] for s in equipo_stats["statistics"]
        }
    
    # 5️⃣ OBTENER LINEUPS
    lineups_data = service.get_fixture_lineups(fixture_id, force_refresh=False)
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
    
    # 6️⃣ OBTENER ESTADÍSTICAS DE TEMPORADA (BATCH)
    both_stats = await get_both_teams_stats_cached(
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        league_id=league_id,
        season=season,
        force_refresh=force_refresh
    )
    
    home_stats = both_stats["home"]
    away_stats = both_stats["away"]
    
    # 7️⃣ CONSTRUIR RESPUESTA FINAL (CON COLORES)
    return {
        "fixture_id": fixture["id"],
        "fecha": fixture["date"],
        "liga": league["name"],
        "pais": league["country"],
        "temporada": season,
        "equipos": {
            "local": {
                "nombre": teams["home"]["name"],
                "logo": home_logo,
                "colores": home_colors,  # 🎨 NUEVO
                "estadisticas_temporada": home_stats
            },
            "visitante": {
                "nombre": teams["away"]["name"],
                "logo": away_logo,
                "colores": away_colors,  # 🎨 NUEVO
                "estadisticas_temporada": away_stats
            }
        },
        "marcador": {
            "local": goals["home"],
            "visitante": goals["away"]
        },
        "estado": status["long"],
        "minuto": status["elapsed"],
        "eventos": eventos,
        "estadisticas_partido": estadisticas,
        "lineups": lineups,
        "lineups_disponibles": len(lineups) > 0
    }


@router.get("/lineups/{fixture_id}", response_model=LineupResponse)
async def get_match_lineups(
    fixture_id: int,
    force_refresh: bool = Query(False, description="Forzar actualización desde API"),
    service: FootballFirebaseService = Depends(get_football_service)
):
    """
    Obtiene las alineaciones (lineups) de un partido.
    
    - **fixture_id**: ID del partido
    - **force_refresh**: Forzar actualización desde API
    - **Incluye**: Titulares, suplentes, formación, entrenador
    - **Cache**: 1 hora en Firebase (las alineaciones no cambian durante el partido)
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
    match_data = service.get_fixture_by_id(fixture_id, force_refresh=False)
    
    if match_data.get("results", 0) == 0:
        raise HTTPException(404, "No se encontró el partido")
    
    match = match_data["response"][0]
    teams = match["teams"]
    
    # Alineaciones
    lineups_data = service.get_fixture_lineups(fixture_id, force_refresh=force_refresh)
    
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
    """
    Pregunta al comentarista IA sobre un partido específico.
    
    - **match_id**: ID del partido
    - **question**: Pregunta del usuario
    - **Cache**: Usa datos de Firebase automáticamente
    """
    # Obtener datos del cache de Firebase
    match_data = get_match_data_from_firebase(match_id)
    
    if not match_data:
        # Forzar actualización
        await refresh_match_data(match_id, force=True)
        match_data = get_match_data_from_firebase(match_id)
    
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
    - **Cache**: Usa Firebase automáticamente (60 segundos)
    - **Actualización**: Detecta cambios automáticamente
    """
    # Intentar obtener datos del cache de Firebase
    current_data = get_match_data_from_firebase(match_id)
    
    if not current_data:
        try:
            await refresh_match_data(match_id, force=True)
            current_data = get_match_data_from_firebase(match_id)
        except Exception as e:
            raise HTTPException(
                503, 
                detail=f"No se pudo obtener información del partido {match_id} desde la API externa: {str(e)}"
            )
    
    if not current_data:
        raise HTTPException(
            404, 
            detail=f"No hay información disponible para el partido {match_id}."
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
    - **Cache**: 2 horas en Firebase
    """
    result = await trivia_service.generate_trivia(
        team1=payload.team1,
        team2=payload.team2,
        num_questions=10
    )
    
    return result


# ===== ENDPOINTS: TEAM STATISTICS =====

@router.get("/team-stats/{team_name}")
async def get_team_statistics_by_name(
    team_name: str,
    season: Optional[int] = Query(None, description="Temporada específica (ej: 2024)"),
    league_name: Optional[str] = Query(None, description="Nombre de la liga (opcional)"),
    force_refresh: bool = Query(False, description="Forzar actualización desde API"),
    service: FootballFirebaseService = Depends(get_football_service)
):
    """
    Obtiene estadísticas de un equipo por nombre.
    
    - **team_name**: Nombre del equipo (ej: "Barcelona")
    - **season**: Temporada opcional (ej: 2024)
    - **league_name**: Nombre de la liga opcional
    - **force_refresh**: Forzar actualización desde API
    - **Cache**: 2 horas en Firebase
    """
    normalized = team_name.strip().lower()

    # Buscar equipo
    team_search = service.search_team_by_name(normalized, force_refresh=force_refresh)

    if not team_search or team_search.get("results", 0) == 0:
        raise HTTPException(404, f"No se encontró el equipo '{team_name}'")

    team_info = team_search["response"][0]
    team_id = team_info["team"]["id"]
    team_real_name = team_info["team"]["name"]
    team_logo = team_info["team"].get("logo")
    team_country = team_info["team"].get("country")

    # Obtener temporadas disponibles
    try:
        seasons_response = service.get_team_seasons(team_id, force_refresh=force_refresh)
        
        if not seasons_response or seasons_response.get("results", 0) == 0:
            raise HTTPException(
                404,
                f"No se encontraron temporadas disponibles para '{team_real_name}'"
            )
        
        available_seasons = seasons_response["response"]
        
    except Exception as e:
        raise HTTPException(500, f"Error al obtener temporadas: {str(e)}")

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

    # Buscar ligas
    try:
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

    except Exception as e:
        raise HTTPException(500, f"Error al buscar ligas: {str(e)}")

    # Seleccionar liga
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
                f"No se encontró la liga '{league_name}'. Ligas disponibles: {', '.join(available_names)}"
            )
    else:
        selected_league = available_leagues[0]
        league_id = selected_league["league_id"]

    # Obtener estadísticas (con cache de Firebase - 2 horas)
    try:
        stats_data = service.get_team_statistics(
            team_id=team_id,
            league_id=league_id,
            season=season,
            force_refresh=force_refresh
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

    # Formatear respuesta
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
        ],
        "cached_from_firebase": not force_refresh
    }

    return {"cached": not force_refresh, "data": result}


# Reemplaza el endpoint /stream-events en tus rutas

@router.get("/stream-events/{fixture_id}")
async def stream_fixture_events(
    fixture_id: int,
    poll_interval: float = Query(10.0, description="Intervalo de polling en segundos", ge=5.0, le=60.0),
    stream_service: StreamService = Depends(get_stream_service)
):
    """
    Stream de eventos en tiempo real para un partido.
    
    - **fixture_id**: ID del partido
    - **poll_interval**: Intervalo de polling (5-60 segundos)
    - **Keep-alive**: Envía mensajes cada 30 segundos para mantener conexión
    - **Emite eventos SSE cuando**:
        - Hay nuevos eventos (goles, tarjetas, etc.)
        - Cambia el estado del partido (HT, FT, etc.)
    - **Usa Firebase como cache** con TTL de 60 segundos
    
    **Tipos de eventos SSE:**
    - `ready`: Conexión establecida
    - `events`: Nuevos eventos detectados
    - `status`: Solo cambio de estado (sin eventos)
    - `error`: Error en el procesamiento
    - `keep-alive`: Comentarios invisibles para mantener conexión
    
    **Ejemplo de uso (JavaScript):**
    ```javascript
    const eventSource = new EventSource(`/football/stream-events/1379107`);
    
    eventSource.addEventListener('ready', (e) => {
        const data = JSON.parse(e.data);
        console.log('Conectado:', data);
    });
    
    eventSource.addEventListener('events', (e) => {
        const data = JSON.parse(e.data);
        console.log('Nuevos eventos:', data.nuevos);
        // Actualizar UI con nuevos eventos
    });
    
    eventSource.addEventListener('status', (e) => {
        const data = JSON.parse(e.data);
        console.log('Cambio de estado:', data.status);
        // Actualizar estado del partido en UI
    });
    
    eventSource.addEventListener('error', (e) => {
        console.error('Error:', e.data);
    });
    
    // Importante: Cerrar conexión cuando termina el partido o no se necesita más
    // eventSource.close();
    ```
    """
    return StreamingResponse(
        stream_service.stream_match_events(
            fixture_id=fixture_id,
            poll_interval=poll_interval
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Para NGINX
            "Content-Type": "text/event-stream",
            "Transfer-Encoding": "chunked"
        }
    )