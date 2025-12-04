"""Servicio mock para simular streaming de eventos"""
import json
import asyncio
import random
from typing import AsyncGenerator, List, Dict, Any
from datetime import datetime


class mockStreamService:
    """Servicio para simular eventos de partido en tiempo real"""
    
    # Eventos posibles para simular con frecuencias realistas
    EVENT_TYPES = [
        # Goles (menos frecuentes pero importantes)
        {"tipo": "Goal", "detalle": "Normal Goal", "peso": 8},
        {"tipo": "Goal", "detalle": "Penalty", "peso": 3},
        {"tipo": "Goal", "detalle": "Own Goal", "peso": 1},
        {"tipo": "Goal", "detalle": "Header", "peso": 4},
        {"tipo": "Goal", "detalle": "Free-kick Goal", "peso": 2},
        
        # Tarjetas (más frecuentes)
        {"tipo": "Card", "detalle": "Yellow Card", "peso": 30},
        {"tipo": "Card", "detalle": "Red Card", "peso": 3},
        {"tipo": "Card", "detalle": "Second Yellow Card", "peso": 2},
        
        # Sustituciones (frecuentes)
        {"tipo": "subst", "detalle": "Substitution", "peso": 25},
        
        # VAR (ocasionales)
        {"tipo": "Var", "detalle": "Goal cancelled", "peso": 4},
        {"tipo": "Var", "detalle": "Penalty confirmed", "peso": 3},
        {"tipo": "Var", "detalle": "Goal confirmed", "peso": 5},
        {"tipo": "Var", "detalle": "Red Card after VAR", "peso": 2},
        
        # Otros eventos interesantes
        {"tipo": "Penalty", "detalle": "Penalty awarded", "peso": 5},
        {"tipo": "Missed Penalty", "detalle": "Penalty missed", "peso": 2},
        {"tipo": "Corner", "detalle": "Corner kick", "peso": 15},
        {"tipo": "Offside", "detalle": "Offside", "peso": 12},
        {"tipo": "Injury", "detalle": "Player injured", "peso": 8},
        {"tipo": "Free Kick", "detalle": "Free kick", "peso": 10},
    ]
    
    # Estados del partido
    MATCH_STATES = [
        "First Half",
        "Halftime", 
        "Second Half",
        "Match Finished"
    ]
    
    # Jugadores ficticios con posiciones
    PLAYERS = {
        "delanteros": [
            "Messi", "Cristiano", "Haaland", "Mbappé", "Lewandowski",
            "Benzema", "Kane", "Osimhen", "Vlahovic", "Núñez"
        ],
        "mediocampistas": [
            "De Bruyne", "Modric", "Kroos", "Bellingham", "Pedri",
            "Gavi", "Rodri", "Casemiro", "Valverde", "Camavinga"
        ],
        "defensas": [
            "Van Dijk", "Rüdiger", "Dias", "Militão", "Koundé",
            "Saliba", "Stones", "Marquinhos", "Kim", "Gabriel"
        ],
        "porteros": [
            "Courtois", "Alisson", "Ter Stegen", "Ederson", "Oblak",
            "Donnarumma", "Neuer", "Maignan"
        ]
    }
    
    def __init__(self):
        self._match_state = {
            "minuto": 0,
            "estado": "First Half",
            "marcador_local": 0,
            "marcador_visitante": 0,
            "eventos_enviados": 0
        }
    
    async def stream_mock_events(
        self,
        fixture_id: int,
        poll_interval: float = 10.0,
        event_probability: float = 0.4,
        goals_probability: float = 0.15,
        cards_probability: float = 0.25,
        team_local: str = "Real Madrid",
        team_visitante: str = "Barcelona"
    ) -> AsyncGenerator[str, None]:
        """
        Simula un stream de eventos de partido.
        
        Args:
            fixture_id: ID del partido (ficticio)
            poll_interval: Intervalo entre actualizaciones
            event_probability: Probabilidad general de evento (0.0 - 1.0)
            goals_probability: Probabilidad específica de gol cuando hay evento (0.0 - 1.0)
            cards_probability: Probabilidad específica de tarjeta cuando hay evento (0.0 - 1.0)
            team_local: Nombre del equipo local
            team_visitante: Nombre del equipo visitante
        
        Yields:
            Mensajes SSE formateados
        """
        # Reset estado
        self._match_state = {
            "minuto": 0,
            "estado": "First Half",
            "marcador_local": 0,
            "marcador_visitante": 0,
            "eventos_enviados": 0
        }
        
        # Evento de conexión
        yield self._format_sse_event(
            event_type="ready",
            data={
                "fixture_id": fixture_id,
                "status": "mock_listening",
                "initial_status": {
                    "estado": self._match_state["estado"],
                    "minuto": self._match_state["minuto"],
                    "marcador_local": self._match_state["marcador_local"],
                    "marcador_visitante": self._match_state["marcador_visitante"]
                },
                "teams": {
                    "local": team_local,
                    "visitante": team_visitante
                }
            }
        )
        
        # Simular partido completo (90 minutos)
        while self._match_state["minuto"] < 95:
            await asyncio.sleep(poll_interval)
            
            # Avanzar tiempo
            self._advance_time()
            
            # Actualizar estado del partido
            status_changed = self._update_match_state()
            
            # Decidir si generar evento
            should_generate_event = random.random() < event_probability
            
            new_events = []
            if should_generate_event:
                event = self._generate_random_event(
                    fixture_id, 
                    team_local, 
                    team_visitante,
                    goals_probability,
                    cards_probability
                )
                new_events.append(event)
                self._match_state["eventos_enviados"] += 1
            
            # Emitir solo si hay cambios
            if new_events or status_changed:
                event_type = "events" if new_events else "status"
                
                yield self._format_sse_event(
                    event_type=event_type,
                    data={
                        "fixture_id": fixture_id,
                        "nuevos": new_events,
                        "status": {
                            "estado": self._match_state["estado"],
                            "minuto": self._match_state["minuto"],
                            "marcador_local": self._match_state["marcador_local"],
                            "marcador_visitante": self._match_state["marcador_visitante"]
                        }
                    }
                )
        
        # Evento final
        yield self._format_sse_event(
            event_type="status",
            data={
                "fixture_id": fixture_id,
                "nuevos": [],
                "status": {
                    "estado": "Match Finished",
                    "minuto": 90,
                    "marcador_local": self._match_state["marcador_local"],
                    "marcador_visitante": self._match_state["marcador_visitante"]
                }
            }
        )
    
    def _advance_time(self):
        """Avanza el reloj del partido"""
        increment = random.randint(1, 3)
        self._match_state["minuto"] += increment
    
    def _update_match_state(self) -> bool:
        """
        Actualiza el estado del partido según el minuto.
        Retorna True si cambió el estado.
        """
        old_state = self._match_state["estado"]
        minuto = self._match_state["minuto"]
        
        if minuto >= 90:
            self._match_state["estado"] = "Match Finished"
        elif minuto >= 45 and minuto < 46:
            self._match_state["estado"] = "Halftime"
        elif minuto >= 46:
            self._match_state["estado"] = "Second Half"
        else:
            self._match_state["estado"] = "First Half"
        
        return old_state != self._match_state["estado"]
    
    def _generate_random_event(
        self, 
        fixture_id: int,
        team_local: str,
        team_visitante: str,
        goals_probability: float = 0.15,
        cards_probability: float = 0.25
    ) -> Dict[str, Any]:
        """
        Genera un evento aleatorio con probabilidades configurables.
        
        Args:
            goals_probability: Peso adicional para goles
            cards_probability: Peso adicional para tarjetas
        """
        # Ajustar pesos según probabilidades configuradas
        adjusted_events = []
        for event_type in self.EVENT_TYPES:
            weight = event_type["peso"]
            
            # Aumentar peso de goles según probabilidad
            if event_type["tipo"] == "Goal":
                weight = int(weight * (1 + goals_probability * 5))
            
            # Aumentar peso de tarjetas según probabilidad
            elif event_type["tipo"] == "Card":
                weight = int(weight * (1 + cards_probability * 3))
            
            adjusted_events.append({
                **event_type,
                "peso_ajustado": weight
            })
        
        # Seleccionar tipo de evento (weighted random)
        weights = [e["peso_ajustado"] for e in adjusted_events]
        event_template = random.choices(adjusted_events, weights=weights)[0]
        
        # Seleccionar equipo aleatorio (con ventaja local)
        is_local = random.random() < 0.55  # 55% probabilidad equipo local
        equipo = team_local if is_local else team_visitante
        
        # Seleccionar jugador según tipo de evento
        jugador = self._select_player_for_event(event_template["tipo"])
        
        # Crear evento
        event = {
            "minuto": self._match_state["minuto"],
            "equipo": equipo,
            "jugador": jugador,
            "tipo": event_template["tipo"],
            "detalle": event_template["detalle"]
        }
        
        # Si es gol, actualizar marcador
        if event_template["tipo"] == "Goal" and "cancelled" not in event_template["detalle"].lower():
            if is_local:
                self._match_state["marcador_local"] += 1
            else:
                self._match_state["marcador_visitante"] += 1
        
        # Si es gol anulado por VAR, restar gol
        if event_template["tipo"] == "Var" and "cancelled" in event_template["detalle"].lower():
            if is_local and self._match_state["marcador_local"] > 0:
                self._match_state["marcador_local"] -= 1
            elif not is_local and self._match_state["marcador_visitante"] > 0:
                self._match_state["marcador_visitante"] -= 1
        
        # Si es tarjeta, agregar apuesta
        if event_template["tipo"] == "Card":
            event["apuesta"] = random.randint(1, 100)
        
        # Si es penalti confirmado, hay posibilidad de gol
        if event_template["tipo"] == "Var" and "Penalty confirmed" in event_template["detalle"]:
            # 75% probabilidad de convertir el penalti
            if random.random() < 0.75:
                if is_local:
                    self._match_state["marcador_local"] += 1
                else:
                    self._match_state["marcador_visitante"] += 1
                event["detalle"] += " - Converted"
        
        return event
    
    def _select_player_for_event(self, event_type: str) -> str:
        """Selecciona un jugador apropiado según el tipo de evento"""
        all_players = (
            self.PLAYERS["delanteros"] + 
            self.PLAYERS["mediocampistas"] + 
            self.PLAYERS["defensas"] + 
            self.PLAYERS["porteros"]
        )
        
        if event_type == "Goal":
            # Goles: 70% delanteros, 25% mediocampistas, 5% defensas
            pool = (
                self.PLAYERS["delanteros"] * 7 +
                self.PLAYERS["mediocampistas"] * 2 +
                self.PLAYERS["defensas"]
            )
            return random.choice(pool)
        
        elif event_type == "Card":
            # Tarjetas: más probable en defensas y mediocampistas
            pool = (
                self.PLAYERS["defensas"] * 3 +
                self.PLAYERS["mediocampistas"] * 2 +
                self.PLAYERS["delanteros"]
            )
            return random.choice(pool)
        
        elif event_type == "subst":
            # Sustituciones: cualquier jugador excepto porteros
            pool = (
                self.PLAYERS["delanteros"] + 
                self.PLAYERS["mediocampistas"] + 
                self.PLAYERS["defensas"]
            )
            return random.choice(pool)
        
        elif event_type == "Injury":
            # Lesiones: cualquier jugador
            return random.choice(all_players)
        
        else:
            # Otros eventos: cualquier jugador de campo
            pool = (
                self.PLAYERS["delanteros"] + 
                self.PLAYERS["mediocampistas"] + 
                self.PLAYERS["defensas"]
            )
            return random.choice(pool)
    
    def _format_sse_event(self, event_type: str, data: Dict) -> str:
        """Formatea un mensaje SSE"""
        return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
    
    async def stream_mock_events_fast(
        self,
        fixture_id: int,
        total_events: int = 20,
        interval: float = 2.0,
        goals_probability: float = 0.2,
        cards_probability: float = 0.3,
        team_local: str = "Real Madrid",
        team_visitante: str = "Barcelona"
    ) -> AsyncGenerator[str, None]:
        """
        Versión rápida: genera eventos cada X segundos sin importar el tiempo del partido.
        Ideal para testing rápido.
        
        Args:
            fixture_id: ID del partido
            total_events: Número total de eventos a generar
            interval: Segundos entre eventos
            goals_probability: Probabilidad aumentada para goles
            cards_probability: Probabilidad aumentada para tarjetas
            team_local: Equipo local
            team_visitante: Equipo visitante
        """
        # Reset
        self._match_state = {
            "minuto": 0,
            "estado": "First Half",
            "marcador_local": 0,
            "marcador_visitante": 0,
            "eventos_enviados": 0
        }
        
        # Evento ready
        yield self._format_sse_event(
            event_type="ready",
            data={
                "fixture_id": fixture_id,
                "status": "mock_fast_mode",
                "mode": "fast",
                "total_events": total_events,
                "teams": {
                    "local": team_local,
                    "visitante": team_visitante
                }
            }
        )
        
        # Generar eventos
        for i in range(total_events):
            await asyncio.sleep(interval)
            
            # Avanzar tiempo ficticios
            self._match_state["minuto"] = min(5 + (i * 4), 90)
            self._update_match_state()
            
            # Generar evento
            event = self._generate_random_event(
                fixture_id, 
                team_local, 
                team_visitante,
                goals_probability,
                cards_probability
            )
            
            yield self._format_sse_event(
                event_type="events",
                data={
                    "fixture_id": fixture_id,
                    "nuevos": [event],
                    "status": {
                        "estado": self._match_state["estado"],
                        "minuto": self._match_state["minuto"],
                        "marcador_local": self._match_state["marcador_local"],
                        "marcador_visitante": self._match_state["marcador_visitante"]
                    }
                }
            )
        
        # Finalizar
        yield self._format_sse_event(
            event_type="status",
            data={
                "fixture_id": fixture_id,
                "nuevos": [],
                "status": {
                    "estado": "Match Finished",
                    "minuto": 90,
                    "marcador_local": self._match_state["marcador_local"],
                    "marcador_visitante": self._match_state["marcador_visitante"]
                }
            }
        )