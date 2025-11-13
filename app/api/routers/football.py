"""Endpoints para datos de fútbol en vivo"""
from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import StreamingResponse
from typing import Optional
import asyncio
import json
from app.schemas.football import (
    MatchInfo, LiveMatchesResponse, MatchEventsResponse,
    FixtureSearchParams, LeaguesResponse, League,
    LineupResponse, TeamLineup, LineupPlayer 
)
from app.services.football_service import FootballAPIService
from app.core.config import get_settings
from app.core.cache import cache_manager

router = APIRouter(prefix="/football", tags=["Football Live Data"])

def get_football_service() -> FootballAPIService:
    """Dependency para obtener el servicio de fútbol"""
    settings = get_settings()
    # Asegúrate de agregar FOOTBALL_API_KEY a tu config
    api_key = getattr(settings, 'FOOTBALL_API_KEY', "0e88fe12ff5324e08d0dd7b35659829e")
    return FootballAPIService(api_key)

@router.get("/live-matches", response_model=LiveMatchesResponse)
async def get_live_matches(
    service: FootballAPIService = Depends(get_football_service)
):
    """
    Obtiene todos los partidos que están en vivo actualmente.
    
    - **Caché**: 60 segundos
    - **Retorna**: Lista completa de partidos en vivo con información básica
    """
    data = service.get_live_fixtures()
    
    if data.get("results", 0) == 0:
        return {
            "total": 0,
            "matches": [],
        }
    
    matches = []
    for match in data["response"]:
        match_info = service.format_match_info(match)
        matches.append(match_info)
    
    return {"total": len(matches), "matches": matches}

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
    eventos_previos = cache_manager.get_last_events(fixture_id)
    nuevo_evento = len(eventos) > len(eventos_previos)
    if nuevo_evento:
        cache_manager.set_last_events(fixture_id, eventos)
    
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
    eventos_raw = service.get_fixture_events(fixture_id)
    eventos_norm = [service.normalize_event(e) for e in eventos_raw]
    eventos_norm.sort(key=lambda x: (x["minuto"] if x["minuto"] is not None else -1))
    
    # Actualizar caché
    cache_manager.set_last_events(fixture_id, eventos_norm)
    
    # Limpiar _key antes de responder
    resp = [{
        "minuto": e["minuto"],
        "equipo": e["equipo"],
        "jugador": e["jugador"],
        "tipo": e["tipo"],
        "detalle": e["detalle"]
    } for e in eventos_norm]
    
    return {
        "fixture_id": fixture_id,
        "eventos": resp,
        "total": len(resp)
    }

@router.get("/stream-events/{fixture_id}")
async def stream_match_events(
    fixture_id: int,
    poll_sec: float = Query(default=2.0, ge=0.5, le=10.0),
    service: FootballAPIService = Depends(get_football_service)
):
    """
    Server-Sent Events: Stream de eventos nuevos en tiempo real.
    
    - **fixture_id**: ID del partido a seguir
    - **poll_sec**: Intervalo de polling en segundos (0.5-10.0)
    - **Formato**: SSE con eventos tipo 'ready', 'events' y 'error'
    
    ### Ejemplo de uso (JavaScript):
```javascript
    const eventSource = new EventSource('/football/stream-events/12345?poll_sec=2');
    
    eventSource.addEventListener('ready', (e) => {
        console.log('Connected:', JSON.parse(e.data));
    });
    
    eventSource.addEventListener('events', (e) => {
        const data = JSON.parse(e.data);
        console.log('New events:', data.nuevos);
    });
```
    """
    async def event_generator():
        # Inicializar baseline
        if fixture_id not in cache_manager.get_last_events(fixture_id):
            try:
                base_raw = service.get_fixture_events(fixture_id)
                base_norm = [service.normalize_event(e) for e in base_raw]
                base_norm.sort(key=lambda x: (x["minuto"] if x["minuto"] is not None else -1))
                cache_manager.set_last_events(fixture_id, base_norm)
            except Exception:
                cache_manager.set_last_events(fixture_id, [])
        
        # Notificar conexión establecida
        yield f"event: ready\ndata: {json.dumps({'fixture_id': fixture_id, 'status': 'listening'})}\n\n"
        
        while True:
            try:
                eventos_raw = service.get_fixture_events(fixture_id)
                eventos_norm = [service.normalize_event(e) for e in eventos_raw]
                eventos_norm.sort(key=lambda x: (x["minuto"] if x["minuto"] is not None else -1))
                
                nuevos = service.diff_new_events(fixture_id, eventos_norm)
                
                if nuevos:
                    payload = [{
                        "minuto": e["minuto"],
                        "equipo": e["equipo"],
                        "jugador": e["jugador"],
                        "tipo": e["tipo"],
                        "detalle": e["detalle"]
                    } for e in nuevos]
                    
                    yield f"event: events\ndata: {json.dumps({'fixture_id': fixture_id, 'nuevos': payload})}\n\n"
            
            except Exception as ex:
                yield f"event: error\ndata: {json.dumps({'message': str(ex)})}\n\n"
            
            await asyncio.sleep(poll_sec)
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Para Nginx
        }
    )

@router.get("/find-fixture")
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
    - **Incluye**: 
        - Formación táctica (ej: 4-4-2)
        - Jugadores titulares (startXI) con posiciones en el campo
        - Jugadores suplentes
        - Información del entrenador
        - Colores de camisetas
    - **Caché**: 1 hora
    
    ### Información de posiciones:
    - **pos**: G (Portero), D (Defensa), M (Mediocampista), F (Delantero)
    - **grid**: Posición en cuadrícula (ej: "1:1" = fila 1, columna 1)
    - **position.x/y**: Coordenadas para dibujar en canvas
    
    ### Ejemplo:
    - `/football/lineups/215662` - Alineaciones de un partido específico
    """
    # Obtener información básica del partido
    match_data = service.get_fixture_by_id(fixture_id)
    
    if match_data.get("results", 0) == 0:
        raise HTTPException(404, "No se encontró el partido")
    
    match = match_data["response"][0]
    teams = match["teams"]
    
    # Obtener lineups
    lineups_data = service.get_fixture_lineups(fixture_id)
    
    if not lineups_data:
        raise HTTPException(
            404, 
            "No hay alineaciones disponibles para este partido. "
            "Las alineaciones solo están disponibles cuando el partido ha comenzado o está próximo a comenzar."
        )
    
    # Procesar lineups
    lineups_processed = []
    total_players = 0
    
    for lineup in lineups_data:
        team = lineup.get("team", {})
        coach = lineup.get("coach", {})
        formation = lineup.get("formation")
        colors = lineup.get("colors", {})
        
        # Procesar jugadores titulares
        startXI = []
        for player_data in lineup.get("startXI", []):
            player = player_data.get("player", {})
            startXI.append({
                "id": player.get("id"),
                "name": player.get("name"),
                "number": player.get("number"),
                "pos": player.get("pos") or "Unknown"
,
                "grid": player.get("grid"),
                "position": {
                    "x": player.get("x"),
                    "y": player.get("y")
                } if player.get("x") is not None else None
            })
        
        # Procesar suplentes
        substitutes = []
        for player_data in lineup.get("substitutes", []):
            player = player_data.get("player", {})
            substitutes.append({
                "id": player.get("id"),
                "name": player.get("name"),
                "number": player.get("number"),
                "pos": player.get("pos") or "Unknown"
,
                "grid": player.get("grid"),
                "position": None
            })
        
        total_players += len(startXI) + len(substitutes)
        
        lineups_processed.append({
            "team_id": team.get("id"),
            "team_name": team.get("name"),
            "formation": formation,
            "coach_id": coach.get("id"),
            "coach_name": coach.get("name"),
            "coach_photo": coach.get("photo"),
            "colors": colors,
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


@router.get("/match-complete/{fixture_id}")
async def get_complete_match_info(
    fixture_id: int,
    service: FootballAPIService = Depends(get_football_service)
):
    """
    ENDPOINT TODO-EN-UNO: Obtiene TODA la información de un partido.
    
    - **fixture_id**: ID del partido
    - **Incluye**: 
        - Información básica del partido
        - Eventos (goles, tarjetas, sustituciones)
        - Estadísticas
        - Alineaciones (si están disponibles)
    
    ### Perfecto para:
    - Pantallas de partido completo
    - Aplicaciones que necesitan toda la información de una vez
    - Reducir número de llamadas a la API
    
    ### Ejemplo:
    - `/football/match-complete/215662`
    """
    # 1. Información básica del partido
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
    
    # 2. Estadísticas
    stats_data = service.get_fixture_statistics(fixture_id)
    estadisticas = {}
    for equipo_stats in stats_data:
        equipo = equipo_stats["team"]["name"]
        estadisticas[equipo] = {
            s["type"]: s["value"] for s in equipo_stats["statistics"]
        }
    
    # 3. Eventos
    eventos = [{
        "minuto": e["time"]["elapsed"],
        "equipo": e["team"]["name"],
        "jugador": e["player"]["name"] if e["player"] else None,
        "tipo": e["type"],
        "detalle": e["detail"]
    } for e in events]
    
    # 4. Alineaciones (opcional, pueden no estar disponibles)
    lineups_data = service.get_fixture_lineups(fixture_id)
    lineups = []
    
    if lineups_data:
        for lineup in lineups_data:
            team = lineup.get("team", {})
            coach = lineup.get("coach", {})
            
            startXI = []
            for player_data in lineup.get("startXI", []):
                player = player_data.get("player", {})
                startXI.append({
                    "id": player.get("id"),
                    "name": player.get("name"),
                    "number": player.get("number"),
                    "pos": player.get("pos"),
                    "grid": player.get("grid")
                })
            
            substitutes = []
            for player_data in lineup.get("substitutes", []):
                player = player_data.get("player", {})
                substitutes.append({
                    "id": player.get("id"),
                    "name": player.get("name"),
                    "number": player.get("number"),
                    "pos": player.get("pos")
                })
            
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
            "visitante": teams["away"]["name"]
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