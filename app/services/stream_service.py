"""Servicio para streaming de eventos de partidos"""
import json
import asyncio
import random
from typing import AsyncGenerator, List, Dict, Any
from app.core.cache import events_cache, events_history
from app.services.football_service import FootballAPIService


class StreamService:
    """Servicio para streaming de eventos en tiempo real"""
    
    def __init__(self, football_service: FootballAPIService):
        self.football_service = football_service
    
    async def stream_match_events(
        self,
        fixture_id: int,
        poll_interval: float = 10.0
    ) -> AsyncGenerator[str, None]:
        """
        Genera un stream de eventos Server-Sent Events (SSE).
        
        Args:
            fixture_id: ID del partido
            poll_interval: Intervalo de polling en segundos
            
        Yields:
            Mensajes SSE formateados
        """
        # Inicializar baseline de eventos
        await self._initialize_baseline(fixture_id)
        baseline = events_history.get_last_events(fixture_id)
        
        # Enviar evento de conexión exitosa
        yield self._format_sse_event(
            event_type="ready",
            data={"fixture_id": fixture_id, "status": "listening"}
        )
        
        # Loop infinito de polling
        while True:
            try:
                # Obtener eventos actuales
                current_events = await self._get_current_events(fixture_id)
                
                # Detectar nuevos eventos
                new_events = self._get_new_events(baseline, current_events)
                
                if new_events:
                    # Procesar y enviar nuevos eventos
                    processed_events = self._process_new_events(new_events)
                    
                    yield self._format_sse_event(
                        event_type="events",
                        data={
                            "fixture_id": fixture_id,
                            "nuevos": processed_events
                        }
                    )
                    
                    # Actualizar baseline
                    baseline = current_events[:]
                    events_history.set_last_events(fixture_id, baseline)
                
            except Exception as ex:
                # Enviar error al cliente
                yield self._format_sse_event(
                    event_type="error",
                    data={"message": str(ex)}
                )
            
            # Esperar antes del siguiente polling
            await asyncio.sleep(poll_interval)
    
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
            event_type: Tipo de evento (ready, events, error)
            data: Datos del evento
            
        Returns:
            Mensaje SSE formateado
        """
        return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"