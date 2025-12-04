"""Esquemas Pydantic para la API de fútbol"""
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from datetime import datetime
from app.services.football_firebase_service import FootballFirebaseService
from app.services.firebase_service import firebase_service
from app.core.config import get_settings

class Team(BaseModel):
    """Información de un equipo"""
    local: str
    visitante: str

class Score(BaseModel):
    """Marcador del partido"""
    local: Optional[int] = None
    visitante: Optional[int] = None

class MatchEvent(BaseModel):
    """Evento de un partido"""
    minuto: Optional[int] = None
    equipo: Optional[str] = None
    jugador: Optional[str] = None
    tipo: str
    detalle: Optional[str] = None

class MatchStatus(BaseModel):
    """Estado del partido"""
    estado: str
    minuto: Optional[int] = None

class MatchInfo(BaseModel):
    """Información completa de un partido"""
    fixture_id: int
    fecha: str
    liga: str
    pais: str
    equipos: Team
    marcador: Score
    estado: str
    minuto: Optional[int] = None
    eventos: List[MatchEvent] = []
    estadisticas: Dict[str, Dict[str, Any]] = {}
    nuevo_evento: Optional[bool] = None

class LiveMatchesResponse(BaseModel):
    """Respuesta con lista de partidos en vivo"""
    total: int
    matches: List[MatchInfo]

class MatchEventsResponse(BaseModel):
    """Respuesta con eventos de un partido"""
    fixture_id: int
    eventos: List[MatchEvent]
    total: int

class FixtureSearchParams(BaseModel):
    """Parámetros para buscar un partido"""
    local: str = Field(..., description="Nombre del equipo local")
    visitante: str = Field(..., description="Nombre del equipo visitante")
    liga: str = Field(..., description="Nombre de la liga")

class League(BaseModel):
    """Información de una liga"""
    id: int
    nombre: str
    pais: str
    tipo: str
    temporada_actual: Optional[int] = None
    logo: Optional[str] = None

class LeaguesResponse(BaseModel):
    """Respuesta con lista de ligas"""
    total_ligas: int
    ligas: List[League]

class SSEEventData(BaseModel):
    """Datos para Server-Sent Events"""
    fixture_id: int
    nuevos: List[MatchEvent] = []
    status: Optional[str] = None

class PlayerPosition(BaseModel):
    """Posición del jugador en el campo"""
    x: Optional[int] = None
    y: Optional[int] = None

class LineupPlayer(BaseModel):
    """Jugador en la alineación"""
    id: int
    name: str
    number: int
    pos: str  # Posición: G, D, M, F
    grid: Optional[str] = None  # Posición en grid ej: "1:1"
    position: Optional[PlayerPosition] = None

class TeamColors(BaseModel):
    """Colores del equipo"""
    player: Optional[Dict[str, str]] = None  # primary, number, border
    goalkeeper: Optional[Dict[str, str]] = None

class TeamLineup(BaseModel):
    """Alineación de un equipo"""
    team_id: int
    team_name: str
    formation: Optional[str] = None  # ej: "4-4-2"
    coach_id: Optional[int] = None
    coach_name: Optional[str] = None
    coach_photo: Optional[str] = None
    colors: Optional[TeamColors] = None
    startXI: List[LineupPlayer] = []
    substitutes: List[LineupPlayer] = []

class LineupResponse(BaseModel):
    """Respuesta con las alineaciones del partido"""
    fixture_id: int
    equipos: Dict[str, str]  # local, visitante
    lineups: List[TeamLineup] = []
    total_players: int = 0


# ===== MODELOS BASE =====
class TeamInfo(BaseModel):
    local: str
    visitante: str


class Score(BaseModel):
    local: Optional[int]
    visitante: Optional[int]


class Event(BaseModel):
    minuto: Optional[int]
    equipo: str
    jugador: Optional[str]
    tipo: str
    detalle: str


class EventWithBet(Event):
    """Evento con apuesta aleatoria (solo para tarjetas en stream)"""
    apuesta: Optional[int] = None


# ===== MATCH INFO =====
class MatchInfo(BaseModel):
    fixture_id: int
    fecha: str
    liga: str
    pais: str
    equipos: TeamInfo
    marcador: Score
    estado: str
    minuto: Optional[int]
    eventos: List[Event]
    nuevo_evento: bool
    estadisticas: Dict[str, Dict[str, Any]]


# ===== LIVE MATCHES =====
class LiveMatchesResponse(BaseModel):
    total: int
    matches: List[MatchInfo]


# ===== MATCH EVENTS =====
class MatchEventsResponse(BaseModel):
    fixture_id: int
    eventos: List[Event]
    total: int


# ===== FIXTURE SEARCH =====
class FixtureSearchParams(BaseModel):
    fecha: Optional[str] = None
    local: Optional[str] = None
    visitante: Optional[str] = None
    liga: Optional[str] = None


class FixtureBasicInfo(BaseModel):
    fixture_id: int
    local: str
    visitante: str
    liga: str
    fecha: str
    estado: str
    minuto: Optional[int] = None


class FixturesByDateResponse(BaseModel):
    total: int
    partidos: List[FixtureBasicInfo]


# ===== LEAGUES =====
class League(BaseModel):
    id: int
    nombre: str
    pais: str
    tipo: str
    temporada_actual: Optional[int]
    logo: str


class LeaguesResponse(BaseModel):
    total_ligas: int
    ligas: List[League]


# ===== LINEUPS =====
class PlayerPosition(BaseModel):
    x: Optional[float] = None
    y: Optional[float] = None


class LineupPlayer(BaseModel):
    id: Optional[int]
    name: str
    number: Optional[int]
    pos: str  # "Portero", "Defensa", "Mediocampista", "Delantero"
    grid: Optional[str] = None
    position: Optional[PlayerPosition] = None


class TeamLineup(BaseModel):
    team_id: Optional[int]
    team_name: str
    formation: Optional[str]
    coach_id: Optional[int]
    coach_name: Optional[str]
    coach_photo: Optional[str] = None
    colors: Optional[Dict[str, Any]] = {}
    startXI: List[LineupPlayer]
    substitutes: List[LineupPlayer]


class LineupResponse(BaseModel):
    fixture_id: int
    equipos: TeamInfo
    lineups: List[TeamLineup]
    total_players: int


# ===== COMPLETE MATCH =====
class SimpleLineup(BaseModel):
    """Versión simplificada para endpoint completo"""
    team_name: str
    formation: Optional[str]
    coach_name: Optional[str]
    startXI: List[Dict[str, Any]]
    substitutes: List[Dict[str, Any]]

class TeamInfoWithLogos(BaseModel):
    local: str
    visitante: str
    local_logo: Optional[str] = None
    visitante_logo: Optional[str] = None

class CompleteMatchResponse(BaseModel):
    fixture_id: int
    fecha: str
    liga: str
    pais: str
    equipos: TeamInfoWithLogos  # <-- usar la versión con logos
    marcador: Score
    estado: str
    minuto: Optional[int]
    eventos: List[Event]
    estadisticas: Dict[str, Dict[str, Any]]
    lineups: List[SimpleLineup]
    lineups_disponibles: bool


# ===== COMMENTARY & AI =====
class AskRequest(BaseModel):
    question: str


class CommentRequest(BaseModel):
    match_id: int


class CommentaryResponse(BaseModel):
    minute: Optional[int]
    commentary: str
    from_cache: bool


class AskResponse(BaseModel):
    answer: str
    match_context_used: bool


# ===== TRIVIA =====
class TriviaRequest(BaseModel):
    team1: str
    team2: str


class TriviaQuestion(BaseModel):
    question: str
    answer: bool


class TriviaResponse(BaseModel):
    team1: str
    team2: str
    questions: List[TriviaQuestion]
    from_cache: bool


# ===== STREAM EVENTS =====
class StreamReadyEvent(BaseModel):
    fixture_id: int
    status: str

class MatchStatus(BaseModel):
    """Estado actual del partido"""
    estado: str
    minuto: Optional[int] = None
    marcador_local: Optional[int] = None
    marcador_visitante: Optional[int] = None
    
class StreamNewEventsData(BaseModel):
    fixture_id: int
    nuevos: List[EventWithBet]
    status: MatchStatus

class StreamErrorEvent(BaseModel):
    message: str
class SimpleMatchInfo(BaseModel):
    fixture_id: int
    fecha: str
    liga: str
    pais: str
    equipos: Dict[str, str]
    marcador: Dict[str, int]
    estado: str
    minuto: Optional[int] = None

class LiveMatchesBasicResponse(BaseModel):
    total: int
    matches: List[SimpleMatchInfo]


class TeamStatsRequest(BaseModel):
    """Parámetros para buscar estadísticas de equipo"""
    team: str = Field(..., description="Nombre del equipo")
    league: int = Field(..., description="ID de la liga")
    season: int = Field(..., description="Temporada (YYYY)")

class PartidosStats(BaseModel):
    """Estadísticas de partidos"""
    jugados: int
    ganados: int
    empatados: int
    perdidos: int

class GolesStats(BaseModel):
    """Estadísticas de goles"""
    favor: int
    contra: int
    diferencia: Optional[int] = None
    promedio_favor: str
    promedio_contra: str

class TeamStatisticsResponse(BaseModel):
    """Respuesta completa de estadísticas de equipo"""
    equipo: Dict[str, Any]
    liga: Dict[str, Any]
    estadisticas: Dict[str, Any]

class TeamSeasonStats(BaseModel):
    """Estadísticas de temporada de un equipo"""
    forma_actual: str
    partidos: Dict[str, Dict[str, int]]
    goles: Dict[str, Dict[str, Any]]
    rachas_maximas: Dict[str, int]
    porterias_cero: Dict[str, int]
    sin_anotar: Dict[str, int]

class SeasonStatsComplete(BaseModel):
    """Estadísticas de temporada completas para ambos equipos"""
    temporada: int
    liga_id: int
    local: Optional[TeamSeasonStats] = None
    visitante: Optional[TeamSeasonStats] = None

class CompleteMatchResponse(BaseModel):
    """Respuesta completa de un partido con TODAS las estadísticas"""
    fixture_id: int
    fecha: str
    liga: str
    pais: str
    equipos: TeamInfoWithLogos
    marcador: Score
    estado: str
    minuto: Optional[int]
    eventos: List[Event]
    estadisticas_partido: Dict[str, Dict[str, Any]]  # Renombrado para claridad
    lineups: List[SimpleLineup]
    lineups_disponibles: bool
    estadisticas_temporada: SeasonStatsComplete  # NUEVO

class TeamSeasonStatsSimple(BaseModel):
    """Estadísticas simplificadas de temporada"""
    partidos_jugados: int
    ganados: int
    empatados: int
    perdidos: int
    goles_favor: int
    goles_contra: int
    diferencia_goles: int
    forma_reciente: str  # Últimos 5 partidos, ej: "WWDLW"
    porterias_cero: int
    rachas: Dict[str, int]

class TeamColors(BaseModel):
    """Colores del equipo extraídos del logo"""
    primary: str  # Color principal en HEX (ej: "#FF0000")
    secondary: str  # Color secundario en HEX (ej: "#0000FF")

class TeamCompleteInfo(BaseModel):
    """Información completa de un equipo en el partido"""
    nombre: str
    logo: Optional[str] = None
    colores: TeamColors  # 🎨 NUEVO
    estadisticas_temporada: Optional[TeamSeasonStatsSimple] = None

class TeamsCompleteInfo(BaseModel):
    """Información de ambos equipos"""
    local: TeamCompleteInfo
    visitante: TeamCompleteInfo

class CompleteMatchResponse(BaseModel):
    """Respuesta completa de un partido con colores"""
    fixture_id: int
    fecha: str
    liga: str
    pais: str
    temporada: int
    equipos: TeamsCompleteInfo
    marcador: Score
    estado: str
    minuto: Optional[int]
    eventos: List[Event]
    estadisticas_partido: Dict[str, Dict[str, Any]]
    lineups: List[SimpleLineup]
    lineups_disponibles: bool