"""Servicio para gestionar la simulación de eventos de partidos"""
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from app.schemas.simulacro import EventoPartido, UsuarioSimulacro


class SimulacroService:
    """Servicio para gestionar usuarios y eventos del simulacro"""
    
    def __init__(self):
        # Eventos predefinidos del partido
        self.eventos: List[EventoPartido] = [
            EventoPartido(
                minuto=81,
                equipo="Colombia",
                jugador="Yáser Asprilla",
                tipo="subst",
                detalle="Substitution 4"
            ),
            EventoPartido(
                minuto=86,
                equipo="Colombia",
                jugador="Jefferson Lerma",
                tipo="Card",
                detalle="Yellow Card"
            ),
            EventoPartido(
                minuto=89,
                equipo="Colombia",
                jugador="Luis Díaz",
                tipo="Goal",
                detalle="Normal Goal"
            )
        ]
        
        # Almacenamiento de usuarios (en producción usar Redis o base de datos)
        self.usuarios: Dict[str, UsuarioSimulacro] = {}
        
        # Configuración
        self.intervalo_request = 5  # segundos
        self.duracion_partido = 120  # minutos (con tiempo extra)
    
    def crear_usuario(self, usuario_id: str, tiempo_inicial: int = 0) -> UsuarioSimulacro:
        """Crea o actualiza un usuario en el simulacro"""
        if usuario_id in self.usuarios:
            # Usuario ya existe, solo actualizamos tiempo si es diferente
            usuario = self.usuarios[usuario_id]
            if tiempo_inicial != usuario.tiempo_actual:
                usuario.tiempo_actual = tiempo_inicial
                usuario.eventos_mostrados = []
        else:
            # Nuevo usuario
            usuario = UsuarioSimulacro(
                usuario_id=usuario_id,
                tiempo_actual=tiempo_inicial,
                ultimo_request=datetime.now().isoformat(),
                eventos_mostrados=[]
            )
            self.usuarios[usuario_id] = usuario
        
        return usuario
    
    def obtener_usuario(self, usuario_id: str) -> Optional[UsuarioSimulacro]:
        """Obtiene información de un usuario"""
        return self.usuarios.get(usuario_id)
    
    def actualizar_tiempo(self, usuario_id: str, nuevo_tiempo: int) -> Optional[UsuarioSimulacro]:
        """Actualiza el tiempo actual de un usuario"""
        usuario = self.usuarios.get(usuario_id)
        if not usuario:
            return None
        
        usuario.tiempo_actual = nuevo_tiempo
        usuario.ultimo_request = datetime.now().isoformat()
        return usuario
    
    def obtener_eventos(self, usuario_id: str) -> tuple[List[EventoPartido], UsuarioSimulacro]:
        """
        Obtiene los eventos que debe ver el usuario según su tiempo actual.
        Avanza el tiempo del usuario automáticamente.
        """
        usuario = self.usuarios.get(usuario_id)
        if not usuario:
            raise ValueError(f"Usuario '{usuario_id}' no encontrado")
        
        # Actualizar timestamp del último request
        ahora = datetime.now()
        usuario.ultimo_request = ahora.isoformat()
        
        # Avanzar el tiempo del usuario (simula paso del tiempo real)
        # En este caso, avanzamos 1 minuto cada 5 segundos
        usuario.tiempo_actual += 1
        if usuario.tiempo_actual > self.duracion_partido:
            usuario.tiempo_actual = self.duracion_partido
        
        # Filtrar eventos que corresponden al tiempo actual del usuario
        # y que no han sido mostrados antes
        eventos_para_mostrar = [
            evento for evento in self.eventos
            if evento.minuto <= usuario.tiempo_actual
            and evento.minuto not in usuario.eventos_mostrados
        ]
        
        # Marcar eventos como mostrados
        for evento in eventos_para_mostrar:
            if evento.minuto not in usuario.eventos_mostrados:
                usuario.eventos_mostrados.append(evento.minuto)
        
        return eventos_para_mostrar, usuario
    
    def verificar_puede_hacer_request(self, usuario_id: str) -> tuple[bool, Optional[str]]:
        """
        Verifica si un usuario puede hacer un request (han pasado 5 segundos).
        Retorna (puede_hacer_request, mensaje_error)
        """
        usuario = self.usuarios.get(usuario_id)
        if not usuario:
            return False, f"Usuario '{usuario_id}' no encontrado"
        
        if not usuario.ultimo_request:
            return True, None
        
        ultimo_request = datetime.fromisoformat(usuario.ultimo_request)
        ahora = datetime.now()
        diferencia = (ahora - ultimo_request).total_seconds()
        
        if diferencia < self.intervalo_request:
            tiempo_restante = self.intervalo_request - diferencia
            return False, f"Debes esperar {tiempo_restante:.1f} segundos antes del próximo request"
        
        return True, None
    
    def eliminar_usuario(self, usuario_id: str) -> bool:
        """Elimina un usuario del simulacro"""
        if usuario_id in self.usuarios:
            del self.usuarios[usuario_id]
            return True
        return False
    
    def obtener_estadisticas(self) -> dict:
        """Obtiene estadísticas del simulacro"""
        usuarios_activos = []
        ahora = datetime.now()
        
        # Considerar activos a usuarios con request en últimos 30 segundos
        for usuario_id, usuario in self.usuarios.items():
            if usuario.ultimo_request:
                ultimo_request = datetime.fromisoformat(usuario.ultimo_request)
                if (ahora - ultimo_request).total_seconds() < 30:
                    usuarios_activos.append(usuario_id)
        
        return {
            "total_usuarios": len(self.usuarios),
            "usuarios_activos": usuarios_activos,
            "eventos_totales": len(self.eventos),
            "eventos_disponibles": self.eventos
        }
    
    def obtener_configuracion(self) -> dict:
        """Obtiene la configuración actual del simulacro"""
        return {
            "intervalo_request_segundos": self.intervalo_request,
            "duracion_partido_minutos": self.duracion_partido,
            "total_eventos": len(self.eventos),
            "eventos": self.eventos
        }
    
    def reiniciar_usuario(self, usuario_id: str) -> Optional[UsuarioSimulacro]:
        """Reinicia el estado de un usuario"""
        usuario = self.usuarios.get(usuario_id)
        if not usuario:
            return None
        
        usuario.tiempo_actual = 0
        usuario.eventos_mostrados = []
        usuario.ultimo_request = datetime.now().isoformat()
        return usuario


# Singleton del servicio
_simulacro_service = None

def get_simulacro_service() -> SimulacroService:
    """Obtiene la instancia del servicio de simulacro"""
    global _simulacro_service
    if _simulacro_service is None:
        _simulacro_service = SimulacroService()
    return _simulacro_service