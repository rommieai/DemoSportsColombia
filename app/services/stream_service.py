"""Servicio para streaming de eventos de partidos con Firebase"""
import json
import asyncio
import random
from typing import AsyncGenerator, List, Dict, Any
from app.services.football_firebase_service import FootballFirebaseService


class StreamService:
    """Servicio para streaming de eventos en tiempo real usando Firebase"""
    
    def __init__(self, football_service: FootballFirebaseService):
        self.football_service = football_service
        # Cache en memoria solo para el estado del partido (ligero)
        self._last_status_cache: Dict[int, Dict] = {}
    
    async def stream_match_events(
        self,
        fixture_id: int,
        poll_interval: float = 10.0
    ) -> AsyncGenerator[str, None]:
        """
        Genera un stream de eventos Server-Sent Events (SSE).
        SOLO emite cuando hay eventos nuevos O cuando cambia el estado.
        Envía keep-alive cada 30 segundos para mantener la conexión.
        
        Args:
            fixture_id: ID del partido
            poll_interval: Intervalo de polling en segundos
            
        Yields:
            Mensajes SSE formateados
        """
        # CAMBIO CLAVE: Primero obtener eventos actuales
        current_events = await self._get_current_events(fixture_id)
        
        # Inicializar/actualizar baseline con eventos ACTUALES
        # Esto marca todos los eventos existentes como "ya vistos"
        await self._update_baseline_events(fixture_id, current_events)
        
        # Obtener estado inicial y guardarlo
        initial_status = await self._get_match_status(fixture_id)
        self._last_status_cache[fixture_id] = initial_status
        
        # Enviar evento de conexión exitosa con estado inicial
        # NO enviamos eventos históricos aquí
        yield self._format_sse_event(
            event_type="ready",
            data={
                "fixture_id": fixture_id,
                "status": "listening",
                "initial_status": initial_status
            }
        )
        
        # Contador para keep-alive
        last_keepalive = asyncio.get_event_loop().time()
        keepalive_interval = 30.0  # Enviar keep-alive cada 30 segundos
        
        # Loop infinito de polling
        while True:
            try:
                current_time = asyncio.get_event_loop().time()
                
                # Obtener estado actual del partido
                current_status = await self._get_match_status(fixture_id)
                
                # Obtener eventos actuales desde Firebase
                current_events = await self._get_current_events(fixture_id)
                
                # Obtener baseline desde Firebase
                baseline = await self._get_baseline_events(fixture_id)
                
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
                    
                    # Actualizar baseline en Firebase si hay nuevos eventos
                    if new_events:
                        await self._update_baseline_events(fixture_id, current_events)
                    
                    # Actualizar cache de estado
                    if status_changed:
                        self._last_status_cache[fixture_id] = current_status
                    
                    # Reset del keep-alive porque enviamos datos
                    last_keepalive = current_time
                
                # 🔥 KEEP-ALIVE: Enviar comentario SSE cada 30 segundos aunque no haya cambios
                elif (current_time - last_keepalive) >= keepalive_interval:
                    # Los comentarios en SSE (líneas que empiezan con ':') no se muestran al cliente
                    # pero mantienen la conexión viva
                    yield f": keep-alive {int(current_time)}\n\n"
                    last_keepalive = current_time
                    print(f"💓 Keep-alive enviado para fixture {fixture_id}")
                
            except Exception as ex:
                # Enviar error al cliente
                yield self._format_sse_event(
                    event_type="error",
                    data={"message": str(ex), "fixture_id": fixture_id}
                )
            
            # Esperar antes del siguiente polling
            await asyncio.sleep(poll_interval)
    
    def _has_status_changed(self, fixture_id: int, current_status: Dict) -> bool:
        """
        Detecta si el estado del partido cambió.
        SOLO detecta cambios en el estado literal del partido.
        """
        last_status = self._last_status_cache.get(fixture_id)
        
        if not last_status:
            return True  # Primera vez, considerarlo como cambio
        
        # SOLO comparar el estado literal del partido
        changed = last_status.get("estado") != current_status.get("estado")
        
        return changed
    
    async def _get_match_status(self, fixture_id: int) -> Dict[str, Any]:
        """Obtiene el estado actual del partido desde Firebase/API"""
        try:
            match_data = self.football_service.get_fixture_by_id(
                fixture_id, 
                force_refresh=False  # Usar cache de Firebase
            )
            
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
        except Exception as e:
            print(f"Error obteniendo estado del partido {fixture_id}: {str(e)}")
            return {
                "estado": "Error",
                "minuto": None,
                "marcador_local": None,
                "marcador_visitante": None
            }
    
    async def _get_baseline_events(self, fixture_id: int) -> List[Dict[str, Any]]:
        """Obtiene el baseline de eventos desde Firebase"""
        doc_id = f"baseline_{fixture_id}"
        
        baseline = self.football_service.fb.get_if_valid(
            self.football_service.COLLECTION_EVENTS,
            doc_id
        )
        
        if not baseline:
            return []
        
        # Validar que todos los eventos tengan _key como string
        validated_baseline = []
        for e in baseline:
            if isinstance(e, dict) and isinstance(e.get("_key"), str):
                validated_baseline.append(e)
            else:
                print(f"⚠️ Evento del baseline inválido: {e}")
        
        return validated_baseline
    
    async def _update_baseline_events(
        self, 
        fixture_id: int, 
        events: List[Dict[str, Any]]
    ) -> None:
        """Actualiza el baseline de eventos en Firebase"""
        doc_id = f"baseline_{fixture_id}"
        
        self.football_service.fb.set_with_ttl(
            self.football_service.COLLECTION_EVENTS,
            doc_id,
            events,
            3600  # 1 hora
        )
        
        print(f"✓ Baseline actualizado con {len(events)} eventos para fixture {fixture_id}")
    
    async def _get_current_events(self, fixture_id: int) -> List[Dict[str, Any]]:
        """Obtiene eventos actuales desde Firebase/API"""
        try:
            raw_events = self.football_service.get_fixture_events(
                fixture_id,
                force_refresh=False  # Usar cache de Firebase (60 segundos)
            )
            
            # Normalizar eventos - esto convierte la estructura de la API a nuestro formato
            normalized = []
            for e in raw_events:
                try:
                    normalized_event = self.football_service.normalize_event(e)
                    # Validar que _key sea un string
                    if isinstance(normalized_event.get("_key"), str):
                        normalized.append(normalized_event)
                    else:
                        print(f"⚠️ Evento con _key inválida (no es string): {normalized_event.get('_key')}")
                except Exception as norm_error:
                    print(f"⚠️ Error normalizando evento: {str(norm_error)}")
                    continue
            
            normalized.sort(key=lambda x: x.get("minuto") or -1)
            
            return normalized
            
        except Exception as e:
            print(f"Error obteniendo eventos actuales {fixture_id}: {str(e)}")
            import traceback
            traceback.print_exc()
            return []
    
    def _get_new_events(
        self,
        baseline: List[Dict],
        current: List[Dict]
    ) -> List[Dict]:
        """Detecta eventos nuevos comparando con baseline usando claves string"""
        try:
            # Crear set de claves del baseline
            baseline_keys = set()
            for e in baseline:
                key = e.get("_key")
                if key and isinstance(key, str):
                    baseline_keys.add(key)
                elif key:
                    print(f"⚠️ Clave del baseline no es string: {type(key)} - {key}")
            
            # Filtrar eventos nuevos
            new_events = []
            for e in current:
                key = e.get("_key")
                if not key:
                    continue
                if not isinstance(key, str):
                    print(f"⚠️ Clave del evento actual no es string: {type(key)} - {key}")
                    continue
                if key not in baseline_keys:
                    new_events.append(e)
            
            return new_events
            
        except Exception as ex:
            print(f"❌ Error en _get_new_events: {str(ex)}")
            import traceback
            traceback.print_exc()
            return []
    
    def _process_new_events(self, events: List[Dict]) -> List[Dict]:
        """Procesa eventos nuevos antes de enviarlos"""
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