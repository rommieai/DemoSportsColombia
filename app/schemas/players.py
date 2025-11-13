"""Esquemas Pydantic para información de jugadores de API-FOOTBALL"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

# ============== PLAYER PROFILE ==============
class PlayerBirth(BaseModel):
    """Información de nacimiento del jugador"""
    date: Optional[str] = None
    place: Optional[str] = None
    country: Optional[str] = None

class PlayerProfile(BaseModel):
    """Perfil completo de un jugador"""
    id: int
    name: str
    firstname: Optional[str] = None
    lastname: Optional[str] = None
    age: Optional[int] = None
    birth: Optional[PlayerBirth] = None
    nationality: Optional[str] = None
    height: Optional[str] = None
    weight: Optional[str] = None
    injured: Optional[bool] = None
    photo: Optional[str] = None

# ============== PLAYER STATISTICS ==============
class TeamInfo(BaseModel):
    """Información básica del equipo"""
    id: int
    name: str
    logo: Optional[str] = None

class LeagueInfo(BaseModel):
    """Información de la liga"""
    id: int
    name: str
    country: Optional[str] = None
    logo: Optional[str] = None
    flag: Optional[str] = None
    season: Optional[int] = None

class Games(BaseModel):
    """Estadísticas de partidos"""
    appearences: Optional[int] = None
    lineups: Optional[int] = None
    minutes: Optional[int] = None
    number: Optional[int] = None
    position: Optional[str] = None
    rating: Optional[str] = None
    captain: Optional[bool] = None

class Substitutes(BaseModel):
    """Estadísticas de sustituciones"""
    in_: Optional[int] = Field(None, alias="in")
    out: Optional[int] = None
    bench: Optional[int] = None

class Shots(BaseModel):
    """Estadísticas de disparos"""
    total: Optional[int] = None
    on: Optional[int] = None

class Goals(BaseModel):
    """Estadísticas de goles"""
    total: Optional[int] = None
    conceded: Optional[int] = None
    assists: Optional[int] = None
    saves: Optional[int] = None

class Passes(BaseModel):
    """Estadísticas de pases"""
    total: Optional[int] = None
    key: Optional[int] = None
    accuracy: Optional[int] = None

class Tackles(BaseModel):
    """Estadísticas de tackleadas"""
    total: Optional[int] = None
    blocks: Optional[int] = None
    interceptions: Optional[int] = None

class Duels(BaseModel):
    """Estadísticas de duelos"""
    total: Optional[int] = None
    won: Optional[int] = None

class Dribbles(BaseModel):
    """Estadísticas de regates"""
    attempts: Optional[int] = None
    success: Optional[int] = None
    past: Optional[int] = None

class Fouls(BaseModel):
    """Estadísticas de faltas"""
    drawn: Optional[int] = None
    committed: Optional[int] = None

class Cards(BaseModel):
    """Estadísticas de tarjetas"""
    yellow: Optional[int] = None
    yellowred: Optional[int] = None
    red: Optional[int] = None

class Penalty(BaseModel):
    """Estadísticas de penales"""
    won: Optional[int] = None
    commited: Optional[int] = None
    scored: Optional[int] = None
    missed: Optional[int] = None
    saved: Optional[int] = None

class PlayerStatistics(BaseModel):
    """Estadísticas completas del jugador"""
    team: TeamInfo
    league: LeagueInfo
    games: Games
    substitutes: Substitutes
    shots: Shots
    goals: Goals
    passes: Passes
    tackles: Tackles
    duels: Duels
    dribbles: Dribbles
    fouls: Fouls
    cards: Cards
    penalty: Penalty

class PlayerStatisticsResponse(BaseModel):
    """Respuesta con estadísticas del jugador"""
    player: PlayerProfile
    statistics: List[PlayerStatistics]

# ============== SQUAD ==============
class SquadPlayer(BaseModel):
    """Jugador en un squad"""
    id: int
    name: str
    age: Optional[int] = None
    number: Optional[int] = None
    position: Optional[str] = None
    photo: Optional[str] = None

class SquadTeam(BaseModel):
    """Equipo con su squad"""
    team: TeamInfo
    players: List[SquadPlayer]

# ============== PLAYER TEAMS ==============
class PlayerTeamSeason(BaseModel):
    """Temporada en un equipo"""
    season: int
    start: Optional[str] = None
    end: Optional[str] = None

class PlayerTeam(BaseModel):
    """Equipo en el historial del jugador"""
    team: TeamInfo
    seasons: List[PlayerTeamSeason]

# ============== SEARCH & LIST ==============
class PlayerSearchResult(BaseModel):
    """Resultado de búsqueda de jugadores"""
    total: int
    page: int
    total_pages: int
    players: List[PlayerProfile]

class SeasonsList(BaseModel):
    """Lista de temporadas disponibles"""
    seasons: List[int]
    total: int

# ============== RESPONSES ==============
class PlayerDetailResponse(BaseModel):
    """Respuesta detallada del jugador"""
    profile: PlayerProfile
    current_team: Optional[str] = None
    position: Optional[str] = None
    photo_url: Optional[str] = None

class PlayerStatsFullResponse(BaseModel):
    """Respuesta completa con todas las estadísticas"""
    player: PlayerProfile
    statistics: List[PlayerStatistics]
    total_goals: int = 0
    total_assists: int = 0
    total_matches: int = 0
    total_minutes: int = 0
    average_rating: Optional[float] = None

class ErrorResponse(BaseModel):
    """Respuesta de error"""
    error: str
    detail: Optional[str] = None
    available_seasons: Optional[List[int]] = None