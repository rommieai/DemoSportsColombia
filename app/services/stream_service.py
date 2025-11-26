"""Servicio para streaming de eventos de partidos"""
import json
import asyncio
import random
from typing import AsyncGenerator, List, Dict, Any, Optional
from app.core.cache import events_cache, events_history
from app.services.football_service import FootballAPIService


class StreamService:
    """Servicio para streaming de eventos en tiempo real"""
    
    def __init__(self, football_service: FootballAPIService):
        self.football_service = football_service
        # Cache para detectar cambios de estado
        self._last_status_cache: Dict[int, Dict] = {}
    
    async def stream_match_events(
        self,
        fixture_id: int,
        poll_interval: float = 10.0
    ) -> AsyncGenerator[str, None]:
        """
        Genera un stream de eventos Server-Sent Events (SSE).
        SOLO emite cuando hay eventos nuevos O cuando cambia el estado.
        
        Args:
            fixture_id: ID del partido
            poll_interval: Intervalo de polling en segundos
            
        Yields:
            Mensajes SSE formateados
        """
        # Inicializar baseline de eventos
        await self._initialize_baseline(fixture_id)
        baseline = events_history.get_last_events(fixture_id)
        
        # Obtener estado inicial y guardarlo
        initial_status = await self._get_match_status(fixture_id)
        self._last_status_cache[fixture_id] = initial_status
        
        # Enviar evento de conexión exitosa con estado inicial
        yield self._format_sse_event(
            event_type="ready",
            data={
                "fixture_id": fixture_id,
                "status": "listening",
                "initial_status": initial_status
            }
        )
        
        # Loop infinito de polling
        while True:
            try:
                # Obtener estado actual del partido
                current_status = await self._get_match_status(fixture_id)
                
                # Obtener eventos actuales
                current_events = await self._get_current_events(fixture_id)
                
                # Detectar nuevos eventos
                new_events = self._get_new_events(baseline, current_events)
                
                # Detectar cambios en el estado
                status_changed = self._has_status_changed(fixture_id, current_status)
                
                # ✅ SOLO emitir si hay eventos nuevos O cambió el estado
                if new_events or status_changed:
                    # Procesar eventos nuevos
                    processed_events = self._process_new_events(new_events) if new_events else []
                    
                    # Determinar tipo de evento
                    if new_events and status_changed:
                        event_type = "events"  # Hay eventos nuevos (prioridad)
                    elif new_events:
                        event_type = "events"  # Solo eventos nuevos
                    else:
                        event_type = "status"  # Solo cambio de estado
                    
                    yield self._format_sse_event(
                        event_type=event_type,
                        data={
                            "fixture_id": fixture_id,
                            "nuevos": processed_events,
                            "status": current_status
                        }
                    )
                    
                    # Actualizar caches
                    if new_events:
                        baseline = current_events[:]
                        events_history.set_last_events(fixture_id, baseline)
                    
                    if status_changed:
                        self._last_status_cache[fixture_id] = current_status
                
                # Si no hay cambios, NO emitimos nada (silencio hasta que haya cambios)
                
            except Exception as ex:
                # Enviar error al cliente
                yield self._format_sse_event(
                    event_type="error",
                    data={"message": str(ex)}
                )
            
            # Esperar antes del siguiente polling
            await asyncio.sleep(poll_interval)
    
    def _has_status_changed(self, fixture_id: int, current_status: Dict) -> bool:
        """
        Detecta si el estado del partido cambió.
        SOLO detecta cambios en el estado literal del partido:
        - "Not Started" → "First Half"
        - "First Half" → "Halftime"
        - "Halftime" → "Second Half"
        - "Second Half" → "Match Finished"
        
        IGNORA: minutos, marcador (esos vienen con los eventos)
        """
        last_status = self._last_status_cache.get(fixture_id)
        
        if not last_status:
            return True  # Primera vez, considerarlo como cambio
        
        # ✅ SOLO comparar el estado literal del partido
        changed = last_status.get("estado") != current_status.get("estado")
        
        return changed
    
    async def _get_match_status(self, fixture_id: int) -> Dict[str, Any]:
        """
        Obtiene el estado actual del partido
        """
        try:
            match_data = self.football_service.get_fixture_by_id(fixture_id)
            
            if match_data.get("results", 0) == 0:
                return {
                    "estado": "Unknown",
                    "minuto": None,
                    "marcador_local": None,
                    "marcador_visitante": None
                }
            
            match = match_data["response"][0]
            fixture = match["fixture"]
            goals = match["goals"]
            status = fixture["status"]
            
            return {
                "estado": status["long"],
                "minuto": status["elapsed"],
                "marcador_local": goals["home"],
                "marcador_visitante": goals["away"]
            }
        except Exception:
            return {
                "estado": "Error",
                "minuto": None,
                "marcador_local": None,
                "marcador_visitante": None
            }
    
    async def _initialize_baseline(self, fixture_id: int) -> None:
        """Inicializa el baseline de eventos si no existe"""
        if not events_history.get_last_events(fixture_id):
            try:
                raw_events = self.football_service.get_fixture_events(fixture_id)
                normalized = [
                    self.football_service.normalize_event(e) 
                    for e in raw_events
                ]
                normalized.sort(
                    key=lambda x: (x["minuto"] if x["minuto"] is not None else -1)
                )
                events_history.set_last_events(fixture_id, normalized)
            except Exception:
                events_history.set_last_events(fixture_id, [])
    
    async def _get_current_events(self, fixture_id: int) -> List[Dict[str, Any]]:
        """Obtiene eventos actuales desde cache o API"""
        # Intentar obtener desde cache
        cached = events_cache.get(f"events:{fixture_id}")
        
        if cached is not None:
            return cached
        
        # Obtener desde API y cachear
        raw_events = self.football_service.get_fixture_events(fixture_id)
        normalized = [
            self.football_service.normalize_event(e) 
            for e in raw_events
        ]
        normalized.sort(key=lambda x: x.get("minuto") or -1)
        
        events_cache.set(f"events:{fixture_id}", normalized)
        return normalized
    
    def _get_new_events(
        self,
        baseline: List[Dict],
        current: List[Dict]
    ) -> List[Dict]:
        """Detecta eventos nuevos comparando con baseline"""
        return [e for e in current if e not in baseline]
    
    def _process_new_events(self, events: List[Dict]) -> List[Dict]:
        """
        Procesa eventos nuevos antes de enviarlos.
        Agrega campo 'apuesta' random para tarjetas.
        """
        processed = []
        
        for event in events:
            item = {
                "minuto": event["minuto"],
                "equipo": event["equipo"],
                "jugador": event["jugador"],
                "tipo": event["tipo"],
                "detalle": event["detalle"]
            }
            
            # Agregar apuesta random para tarjetas
            if event["tipo"] == "Card":
                item["apuesta"] = random.randint(1, 100)
            
            processed.append(item)
        
        return processed
    
    def _format_sse_event(self, event_type: str, data: Dict) -> str:
        """
        Formatea un mensaje Server-Sent Event.
        
        Args:
            event_type: Tipo de evento (ready, events, status, error)
            data: Datos del evento
            
        Returns:
            Mensaje SSE formateado
        """
        return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"