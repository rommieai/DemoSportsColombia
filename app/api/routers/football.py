"""Endpoints para datos de fútbol en vivo"""
from fastapi import APIRouter, HTTPException, Query, Depends, FastAPI, BackgroundTasks
from fastapi.responses import StreamingResponse
from typing import Optional
from app.core.config import get_settings
import openai
from pydantic import BaseModel
import hashlib
from openai import OpenAI
import time
import os
from app.tasks import refresh_match_data
from app.cache_managerask import football_cache
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
openai.api_key = os.getenv("OPENAI_API_KEY") 

class AskRequest(BaseModel):
    question: str

class CommentRequest(BaseModel):
    match_id: int

def get_football_service() -> FootballAPIService:
    """Dependency para obtener el servicio de fútbol"""
    settings = get_settings()
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
@router.get("/fixture-by-date-teams")
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

@router.get("/fixtures-by-date")
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

async def generate_ia_match_events(fixture_id: int):
    settings = get_settings()
    openai.api_key = settings.OPENAI_API_KEY

    prompt = f"""
        Genera un JSON que coincida con la estructura de /match-events/{fixture_id}:
        {{
          "fixture_id": {fixture_id},
          "eventos": [
            {{
              "minuto": <minuto del evento>,
              "equipo": "<Colombia o Australia>",
              "jugador": "<nombre del jugador>",
              "tipo": "<Goal|subst|Card>",
              "detalle": "<detalle del evento>"
            }}
          ],
          "total": <cantidad de eventos>
        }}
        Usa información **real** del partido amistoso entre Colombia y Australia del 18 de noviembre de 2025.
        Incluye goles, sustituciones y tarjetas amarillas/rojas si ocurrieron.
        Si el partido aún no ha empezado, devuelve una lista vacía en "eventos" y "total": 0.
        Solo devuelve JSON válido, nada más.
    """

    response = openai.chat.completions.create(
        model="gpt-5-mini",
        messages=[{"role": "user", "content": prompt}]
    )

    content = response.choices[0].message.content
    return json.loads(content)

class TTLCache:
    def __init__(self):
        self.store = {}  # { key: (timestamp, value) }

    def get(self, key):
        if key not in self.store:
            return None
        ts, value = self.store[key]
        if time.time() - ts > 10:  # 10 segundos de TTL
            return None
        return value

    def set(self, key, value):
        self.store[key] = (time.time(), value)

cache_api = TTLCache()

@router.get("/match-events/{fixture_id}", response_model=MatchEventsResponse)
async def get_match_events(
    fixture_id: int,
    service: FootballAPIService = Depends(get_football_service),
    use_ai_fallback: bool = True
):
    """
    Obtiene un snapshot de todos los eventos actuales del partido.
    
    - **fixture_id**: ID del partido
    - **Uso**: Ideal para primera carga antes de conectarse al stream
    """

    # Intentar obtener eventos desde cache
    eventos_norm = cache_api.get(f"events:{fixture_id}")
    
    if eventos_norm is None:
        # No estaba en cache, llamar a la API
        eventos_raw = service.get_fixture_events(fixture_id)
        if not eventos_raw and use_ai_fallback:
            try:
                print("Usando fallback de IA para generar eventos del partido...")
                result = await generate_ia_match_events(fixture_id)
                return result
            except Exception as e:
                raise HTTPException(
                    status_code=404,
                    detail=f"No se encontraron eventos para fixture {fixture_id} y fallback de IA falló: {str(e)}"
                )

        eventos_norm = [service.normalize_event(e) for e in eventos_raw]
        eventos_norm.sort(key=lambda x: (x["minuto"] if x["minuto"] is not None else -1))

        # Guardar en cache
        cache_api.set(f"events:{fixture_id}", eventos_norm)

    # Actualizar caché global de last_events
    cache_manager.set_last_events(fixture_id, eventos_norm)

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

import random

@router.get("/stream-events/{fixture_id}")
async def stream_match_events(
    fixture_id: int,
    poll_sec: float = Query(default=10.0, ge=10.0, le=10.0),
    service: FootballAPIService = Depends(get_football_service)
):

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

        baseline = cache_manager.get_last_events(fixture_id)

        yield f"event: ready\ndata: {json.dumps({'fixture_id': fixture_id, 'status': 'listening'})}\n\n"

        while True:
            try:
                # Obtener eventos desde cache o backend
                cached = cache_api.get(f"events:{fixture_id}")
                if cached is not None:
                    eventos_norm = cached
                else:
                    eventos_raw = service.get_fixture_events(fixture_id)
                    eventos_norm = [service.normalize_event(e) for e in eventos_raw]
                    eventos_norm.sort(key=lambda x: x.get("minuto") or -1)
                    cache_api.set(f"events:{fixture_id}", eventos_norm)

                # Nuevos eventos
                nuevos = [e for e in eventos_norm if e not in baseline]

                if nuevos:
                    payload = []

                    for e in nuevos:
                        item = {
                            "minuto": e["minuto"],
                            "equipo": e["equipo"],
                            "jugador": e["jugador"],
                            "tipo": e["tipo"],
                            "detalle": e["detalle"]
                        }

                        # 🔥 NUEVA LÓGICA: si es tarjeta (Card), agregar apuesta random
                        if e["tipo"] == "Card":
                            item["apuesta"] = random.randint(1, 100)

                        payload.append(item)

                    yield (
                        "event: events\n"
                        f"data: {json.dumps({'fixture_id': fixture_id, 'nuevos': payload})}\n\n"
                    )

                    baseline = eventos_norm[:]
                    cache_manager.set_last_events(fixture_id, baseline)

            except Exception as ex:
                yield f"event: error\ndata: {json.dumps({'message': str(ex)})}\n\n"

            await asyncio.sleep(poll_sec)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
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

    # Obtener información del partido
    match_data = service.get_fixture_by_id(fixture_id)

    if match_data.get("results", 0) == 0:
        raise HTTPException(404, "No se encontró el partido")

    match = match_data["response"][0]
    teams = match["teams"]

    # Obtener alineaciones
    lineups_data = service.get_fixture_lineups(fixture_id)

    if not lineups_data:
        raise HTTPException(
            404,
            "No hay alineaciones disponibles para este partido. "
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
    
  
    stats_data = service.get_fixture_statistics(fixture_id)
    estadisticas = {}
    for equipo_stats in stats_data:
        equipo = equipo_stats["team"]["name"]
        estadisticas[equipo] = {
            s["type"]: s["value"] for s in equipo_stats["statistics"]
        }
    
    
    eventos = [{
        "minuto": e["time"]["elapsed"],
        "equipo": e["team"]["name"],
        "jugador": e["player"]["name"] if e["player"] else None,
        "tipo": e["type"],
        "detalle": e["detail"]
    } for e in events]
    

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

@router.post("/ask/{match_id}")
async def ask_commentator(match_id: int, req: AskRequest, background_tasks: BackgroundTasks):
    # Lanza actualización en background (no bloquea)
    background_tasks.add_task(refresh_match_data, match_id)

    match_data = football_cache.get(match_id)

    if not match_data:
        # Si aún no hay datos, fuerza fetch inmediato
        await refresh_match_data(match_id)
        match_data = football_cache.get(match_id)

    if not match_data:
        return {"error": "No se pudo obtener información del partido."}

    # Crear prompt estilo comentarista deportivo
    prompt = f"""
Actúa como un comentarista deportivo profesional.
Usa exclusivamente la información de este partido para responder.

Información del partido:
{match_data}

Pregunta del usuario: {req.question}

Responde de forma clara, emocionante y precisa. Las respuestas no pueden tener mas de 70 palabras.
"""

    response = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}]
    )

    return {
        "answer": response.choices[0].message.content,
        "match_context_used": True
    }


# Cache simple de comentarios para no repetir
comment_cache = {}  # {match_id: hash_comentario}
class TTLCommentCache:
    def __init__(self, ttl_seconds=60):
        self.store = {}  # { match_id: (timestamp, comentario_hash, comentario) }
        self.ttl = ttl_seconds

    def get(self, match_id):
        if match_id not in self.store:
            return None
        ts, hash_comment, comentario = self.store[match_id]
        if time.time() - ts > self.ttl:
            del self.store[match_id]
            return None
        return comentario

    def set(self, match_id, comentario):
        hash_comment = hashlib.md5(comentario.encode()).hexdigest()
        self.store[match_id] = (time.time(), hash_comment, comentario)

    def get_last_hash(self, match_id):
        if match_id not in self.store:
            return None
        return self.store[match_id][1]

comment_cache_ttl = TTLCommentCache(ttl_seconds=60)
@router.get("/commentary/{match_id}")
async def get_match_commentary(match_id: int, background_tasks: BackgroundTasks):
    """
    Genera un comentario corto y relevante sobre el partido.
    Cache de comentarios valido 60 segundos.
    """
    # Primero revisar cache
    cached_comment = comment_cache_ttl.get(match_id)
    if cached_comment:
        current_data = football_cache.get(match_id)
        return {
            "minute": current_data.get("minuto") if current_data else None,
            "commentary": cached_comment,
            "from_cache": True
        }

    # Obtener estado actual
    current_data = football_cache.get(match_id)
    if not current_data:
        from app.tasks import refresh_match_data
        await refresh_match_data(match_id)
        current_data = football_cache.get(match_id)

    if not current_data:
        raise HTTPException(404, "No se pudo obtener información del partido.")

    # Últimos eventos
    previous_events = cache_manager.get_last_events(match_id) or []
    current_events = current_data.get("eventos", [])

    # Actualizar cache de last_events
    cache_manager.set_last_events(match_id, current_events)

    # Crear prompt dinámico
    prompt = f"""
Eres un comentarista deportivo profesional.
Genera **una frase corta y precisa** sobre el partido actual.
Si hubo cambios respecto al minuto anterior, destácalos.
Si no hubo cambios, genera un comentario relevante usando estadísticas, alineaciones o información de la liga.
Datos previos:
{previous_events}
Datos actuales:
{current_events}
Datos adicionales del partido:
Liga: {current_data.get('liga')}
Equipos: {current_data['equipos']}
Estadísticas: {current_data.get('estadisticas', {})}
Lineups disponibles: {current_data.get('lineups_disponibles', False)}
"""

    # Llamada a OpenAI
    response = openai.chat.completions.create(
        model="gpt-5-mini",
        messages=[{"role": "user", "content": prompt}]
    )

    commentary = response.choices[0].message.content.strip()

    # Evitar repetir comentario anterior exacto
    last_hash = comment_cache_ttl.get_last_hash(match_id)
    hash_comment = hashlib.md5(commentary.encode()).hexdigest()
    if hash_comment == last_hash:
        commentary = "Continúa el partido sin novedades importantes."

    # Guardar en cache TTL
    comment_cache_ttl.set(match_id, commentary)

    return {
        "minute": current_data.get("minuto"),
        "commentary": commentary,
        "from_cache": False
    }


TRIVIA_CACHE = {}
CACHE_DURATION = 60 * 60 * 2 # 2 horas

class TriviaRequest(BaseModel):
    team1: str
    team2: str

@router.post("/trivia")
async def generate_trivia(payload: TriviaRequest):
    settings = get_settings()
    client = OpenAI(api_key=settings.OPENAI_API_KEY)

    cache_key = f"{payload.team1.lower()}_{payload.team2.lower()}"
    now = time.time()

    # ---- CACHE CHECK ----
    if cache_key in TRIVIA_CACHE:
        entry = TRIVIA_CACHE[cache_key]
        if entry["expires"] > now:
            return {
                "team1": payload.team1,
                "team2": payload.team2,
                "questions": entry["data"],
                "from_cache": True
            }

    # ---- GENERATOR FOR SINGLE QUESTION ----
    async def generate_single_question(team: str):
        prompt = (
            f"Genera UNA sola pregunta de trivia sobre datos curiosos del equipo {team}. "
            f"Formato estricto JSON: "
            f'{{"question": "texto de la pregunta", "answer": true/false}}. '
            f"No agregues texto fuera del JSON. No listas, no explicaciones."
        )

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )

        raw = response.choices[0].message.content.strip()

        try:
            data = json.loads(raw)
        except:
            # fallback mínimo
            data = {"question": raw.replace("\n", " "), "answer": True}

        return data

    # ---- GENERATE 10 QUESTIONS ----
    trivia_questions = []

    for i in range(10):
        current_team = payload.team1 if i % 2 == 0 else payload.team2
        q = await generate_single_question(current_team)
        trivia_questions.append(q)

    # ---- SAVE TO CACHE ----
    TRIVIA_CACHE[cache_key] = {
        "expires": now + CACHE_DURATION,
        "data": trivia_questions
    }

    return {
        "team1": payload.team1,
        "team2": payload.team2,
        "questions": trivia_questions,
        "from_cache": False
    }
