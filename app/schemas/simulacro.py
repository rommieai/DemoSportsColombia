"""Esquemas Pydantic para simulación de eventos de partidos"""
from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime


# ===== MODELOS DE EVENTOS =====

class EventoPartido(BaseModel):
    """Evento individual del partido"""
    minuto: int = Field(..., ge=0, le=120, description="Minuto del evento")
    segundo: int = Field(..., ge=0, le=59, description="Segundo exacto del evento")
    equipo: str = Field(..., description="Nombre del equipo")
    jugador: str = Field(..., description="Nombre del jugador")
    tipo: str = Field(..., description="Tipo de evento: Goal, Card, subst, etc.")
    detalle: str = Field(..., description="Detalle del evento")
    
    @property
    def tiempo_total_segundos(self) -> int:
        """Retorna el tiempo total en segundos desde el inicio del partido"""
        return (self.minuto * 60) + self.segundo
    
    class Config:
        json_schema_extra = {
            "example": {
                "minuto": 89,
                "segundo": 23,
                "equipo": "Colombia",
                "jugador": "Luis Díaz",
                "tipo": "Goal",
                "detalle": "Normal Goal"
            }
        }


# ===== MODELOS PARA USUARIOS =====

class UsuarioSimulacro(BaseModel):
    """Información de un usuario en el simulacro"""
    usuario_id: str = Field(..., description="ID único del usuario")
    tiempo_actual_segundos: int = Field(0, ge=0, description="Segundo actual del usuario desde inicio del partido")
    ultimo_request: Optional[str] = Field(None, description="Timestamp del último request")
    eventos_mostrados: List[int] = Field(default_factory=list, description="IDs de eventos ya mostrados")
    velocidad: float = Field(1.0, description="Velocidad de simulación (1.0 = tiempo real)")
    
    @property
    def minuto_actual(self) -> int:
        """Retorna el minuto actual"""
        return self.tiempo_actual_segundos // 60
    
    @property
    def segundo_actual(self) -> int:
        """Retorna el segundo actual dentro del minuto"""
        return self.tiempo_actual_segundos % 60


class CrearUsuarioRequest(BaseModel):
    """Request para crear un nuevo usuario"""
    usuario_id: str = Field(..., min_length=1, description="ID único del usuario")
    tiempo_inicial_minuto: int = Field(0, ge=0, le=120, description="Minuto inicial del usuario")
    tiempo_inicial_segundo: int = Field(0, ge=0, le=59, description="Segundo inicial del usuario")
    velocidad: float = Field(1.0, gt=0, le=10, description="Velocidad de simulación (1.0 = tiempo real)")
    
    @property
    def tiempo_inicial_segundos(self) -> int:
        """Retorna el tiempo inicial en segundos totales"""
        return (self.tiempo_inicial_minuto * 60) + self.tiempo_inicial_segundo
    
    class Config:
        json_schema_extra = {
            "example": {
                "usuario_id": "user_123",
                "tiempo_inicial_minuto": 80,
                "tiempo_inicial_segundo": 45,
                "velocidad": 1.0
            }
        }


class ActualizarTiempoRequest(BaseModel):
    """Request para actualizar el tiempo de un usuario"""
    minuto: int = Field(..., ge=0, le=120, description="Nuevo minuto actual")
    segundo: int = Field(0, ge=0, le=59, description="Nuevo segundo actual")
    
    @property
    def tiempo_total_segundos(self) -> int:
        """Retorna el tiempo total en segundos"""
        return (self.minuto * 60) + self.segundo


class ActualizarVelocidadRequest(BaseModel):
    """Request para cambiar la velocidad de simulación"""
    velocidad: float = Field(..., gt=0, le=10, description="Nueva velocidad (1.0 = tiempo real)")


# ===== MODELOS DE RESPUESTA =====

class TiempoActualInfo(BaseModel):
    """Información del tiempo actual del usuario"""
    minuto: int
    segundo: int
    total_segundos: int
    formato: str = Field(..., description="Formato MM:SS")


class EventosResponse(BaseModel):
    """Respuesta con eventos del partido"""
    usuario_id: str
    tiempo_actual: TiempoActualInfo
    eventos: List[EventoPartido]
    proximo_request_segundos: int = Field(5, description="Segundos hasta el próximo request")
    mensaje: Optional[str] = None


class UsuarioResponse(BaseModel):
    """Respuesta con información del usuario"""
    usuario_id: str
    tiempo_actual: TiempoActualInfo
    velocidad: float
    ultimo_request: Optional[str]
    eventos_mostrados_count: int
    mensaje: str


class EstadisticasSimulacroResponse(BaseModel):
    """Estadísticas del simulacro"""
    total_usuarios: int
    usuarios_activos: List[str]
    eventos_totales: int
    eventos_disponibles: List[EventoPartido]


class ConfiguracionSimulacroResponse(BaseModel):
    """Configuración actual del simulacro"""
    intervalo_request_segundos: int
    duracion_partido_minutos: int
    duracion_partido_segundos: int
    total_eventos: int
    eventos: List[EventoPartido]