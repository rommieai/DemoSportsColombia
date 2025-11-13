"""Esquemas Pydantic para la API de fútbol"""
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from datetime import datetime

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