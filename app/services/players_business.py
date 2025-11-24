"""Lógica de negocio para operaciones complejas con jugadores"""
from typing import Dict, Any, List, Optional
import json
import random
from datetime import datetime, timedelta
from openai import OpenAI
from app.services.players_service import PlayersAPIService
from app.core.config import get_settings


class PlayersBusinessService:
    """Servicios de alto nivel para jugadores (agregaciones, IA, fallbacks)"""
    
    def __init__(self, api_service: PlayersAPIService):
        self.api_service = api_service
        self.settings = get_settings()
        self.openai_client = OpenAI(api_key=self.settings.OPENAI_API_KEY)
        self.bio_cache: Dict[tuple, Dict] = {}
        self.cache_ttl = timedelta(days=1)
    
    # ============== CALCULATIONS ==============
    def calculate_totals(self, statistics: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calcula totales agregados de estadísticas"""
        totals = {
            "total_goals": 0,
            "total_assists": 0,
            "total_matches": 0,
            "total_minutes": 0,
            "total_yellow_cards": 0,
            "total_red_cards": 0,
            "ratings": []
        }
        
        for stat in statistics:
            games = stat.get("games", {})
            goals = stat.get("goals", {})
            cards = stat.get("cards", {})
            
            totals["total_goals"] += goals.get("total") or 0
            totals["total_assists"] += goals.get("assists") or 0
            totals["total_matches"] += games.get("appearences") or 0
            totals["total_minutes"] += games.get("minutes") or 0
            totals["total_yellow_cards"] += cards.get("yellow") or 0
            totals["total_red_cards"] += cards.get("red") or 0
            
            rating = games.get("rating")
            if rating:
                try:
                    totals["ratings"].append(float(rating))
                except (ValueError, TypeError):
                    pass
        
        if totals["ratings"]:
            totals["average_rating"] = round(sum(totals["ratings"]) / len(totals["ratings"]), 2)
        else:
            totals["average_rating"] = None
        
        del totals["ratings"]
        return totals
    
    # ============== COMPLETE INFO ==============
    def get_complete_player_info(
        self, 
        player_id: int, 
        season: Optional[int] = None
    ) -> Dict[str, Any]:
        """Obtiene perfil + estadísticas + temporadas disponibles"""
        profile = self.api_service.get_player_profile(player_id)
        
        if not profile:
            return None
        
        player_data = profile.get("player", {})
        available_seasons = self.api_service.get_available_seasons(player_id)
        
        if not available_seasons:
            return {
                "perfil": player_data,
                "foto": self.api_service.get_player_photo_url(player_id),
                "estadisticas": None,
                "mensaje": "No hay estadísticas disponibles",
                "temporadas_disponibles": []
            }
        
        if season is None:
            season = max(available_seasons)
        
        stats_data = self.api_service.get_player_statistics(player_id=player_id, season=season)
        
        if stats_data.get("results", 0) == 0:
            return {
                "perfil": player_data,
                "foto": self.api_service.get_player_photo_url(player_id),
                "estadisticas": None,
                "mensaje": f"No hay estadísticas para {season}",
                "temporadas_disponibles": sorted(available_seasons, reverse=True),
                "temporada_solicitada": season
            }
        
        response_data = stats_data["response"][0]
        statistics = response_data.get("statistics", [])
        totals = self.calculate_totals(statistics)
        
        return {
            "perfil": {
                "id": player_data.get("id"),
                "nombre": player_data.get("name"),
                "edad": player_data.get("age"),
                "nacionalidad": player_data.get("nationality"),
                "altura": player_data.get("height"),
                "peso": player_data.get("weight"),
                "foto": self.api_service.get_player_photo_url(player_id)
            },
            "temporada": season,
            "estadisticas_detalladas": statistics,
            "resumen": {
                "goles": totals["total_goals"],
                "asistencias": totals["total_assists"],
                "partidos_jugados": totals["total_matches"],
                "minutos_jugados": totals["total_minutes"],
                "rating_promedio": totals["average_rating"],
                "tarjetas_amarillas": totals["total_yellow_cards"],
                "tarjetas_rojas": totals["total_red_cards"]
            },
            "temporadas_disponibles": sorted(available_seasons, reverse=True)
        }
    
    # ============== AI FEATURES ==============
    def generate_player_news(self, player_name: str) -> Dict[str, Any]:
        """Genera noticia corta sobre un jugador"""
        prompt = (
            f"Escribe un párrafo muy breve sobre una noticia o dato curioso reciente "
            f"del jugador de fútbol {player_name}. Máximo 3-4 líneas, estilo informativo."
        )
        
        try:
            response = self.openai_client.chat.completions.create(
                model=self.settings.OPENAI_MODEL_ID,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=100,
                temperature=0.7
            )
            content = response.choices[0].message.content.strip()
            return {"player": player_name, "news": content}
        except Exception as e:
            return {"error": "No se pudo generar la noticia", "detail": str(e)}
    
    def generate_player_bio(self, player_name: str, team: str) -> Dict[str, Any]:
        """Genera biografía con cache"""
        cache_key = (player_name.lower(), team.lower())
        
        if cache_key in self.bio_cache:
            cache_entry = self.bio_cache[cache_key]
            if cache_entry["expires"] > datetime.utcnow():
                return {
                    "player": player_name,
                    "team": team,
                    "bio": cache_entry["bio"],
                    "cached": True
                }
            else:
                del self.bio_cache[cache_key]
        
        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Eres un experto en fútbol."},
                    {
                        "role": "user",
                        "content": (
                            f"Escribe una biografía clara, objetiva y de máximo 50 palabras "
                            f"sobre el jugador {player_name}, quien juega en el {team}."
                        )
                    }
                ]
            )
            
            bio = response.choices[0].message.content
            
            self.bio_cache[cache_key] = {
                "bio": bio,
                "expires": datetime.utcnow() + self.cache_ttl
            }
            
            return {"player": player_name, "team": team, "bio": bio, "cached": False}
        
        except Exception as e:
            return {"error": str(e)}
    
    # ============== SEARCH WITH AI FALLBACK ==============
    def search_with_fallback(
        self,
        name: str,
        season: Optional[int] = None,
        nationality: Optional[str] = None
    ) -> Dict[str, Any]:
        """Busca jugador en API, con fallback a IA si no existe. SIEMPRE genera biografía."""
        search_data = self.api_service.search_players(name, page=1) or {}
        raw_players = search_data.get("response") or search_data.get("players") or []
        
        def is_valid_player(entry):
            if not isinstance(entry, dict):
                return False
            pl = entry.get("player") or {}
            return pl.get("id") is not None and isinstance(pl.get("name"), str)
        
        players_list = [p for p in raw_players if is_valid_player(p)]
        
        if nationality:
            nat = nationality.strip().lower()
            players_list = [
                p for p in players_list 
                if (p.get("player", {}).get("nationality") or "").strip().lower() == nat
            ]
        
        # Si encontramos jugadores, retornar el primero
        if players_list:
            first = players_list[0]
            player_data = first.get("player", {})
            player_id = player_data.get("id")
            player_name = player_data.get("name")
            
            # ✅ GENERAR BIOGRAFÍA SIEMPRE (antes de verificar estadísticas)
            bio = self._generate_quick_bio(player_name)
            
            available_seasons = self.api_service.get_available_seasons(player_id)
            if not available_seasons:
                response = self._create_minimal_response(player_data, season)
                response["bio"] = bio  # ✅ Agregar bio
                return response
            
            if season is None:
                season = max(available_seasons)
            
            stats_data = self.api_service.get_player_statistics(player_id=player_id, season=season)
            if stats_data.get("results", 0) == 0:
                response = self._create_minimal_response(player_data, season)
                response["bio"] = bio  # ✅ Agregar bio
                return response
            
            response_data = stats_data["response"][0]
            statistics = response_data.get("statistics", [])
            totals = self.calculate_totals(statistics)
            
            return {
                "jugador": {
                    "id": player_id,
                    "nombre": player_name,
                    "nacionalidad": player_data.get("nationality"),
                    "edad": player_data.get("age"),
                    "foto": self.api_service.get_player_photo_url(player_id)
                },
                "temporada": season,
                "goles": totals["total_goals"],
                "asistencias": totals["total_assists"],
                "partidos": totals["total_matches"],
                "minutos": totals["total_minutes"],
                "rating": totals["average_rating"],
                "equipos": [
                    {"nombre": s.get("team", {}).get("name"), "liga": s.get("league", {}).get("name")}
                    for s in statistics
                ],
                "bio": bio  # ✅ Siempre incluye bio
            }
        
        # Fallback: generar con IA (ya incluye bio dentro)
        return self._generate_ai_fallback(name, season, nationality)
    
    def _create_minimal_response(self, player_data: Dict, season: Optional[int]) -> Dict[str, Any]:
        """Respuesta mínima cuando no hay estadísticas (sin bio, se agrega después)"""
        return {
            "jugador": player_data,
            "temporada": season or "2024/2025",
            "goles": 0,
            "asistencias": 0,
            "partidos": 0,
            "minutos": 0,
            "rating": 6.5,
            "equipos": []
        }
    
    def _generate_quick_bio(self, player_name: str) -> str:
        """Genera bio corta con manejo robusto de errores"""
        try:
            response = self.openai_client.chat.completions.create(
                model=self.settings.OPENAI_MODEL_ID,
                messages=[
                    {
                        "role": "system", 
                        "content": "Eres un experto en fútbol que escribe biografías concisas y precisas."
                    },
                    {
                        "role": "user", 
                        "content": (
                            f"Escribe una biografía breve, clara y objetiva del futbolista {player_name}. "
                            f"Incluye nacionalidad, posición, estilo de juego y un logro destacado. "
                            f"Máximo 5 líneas, sin introducciones ni relleno."
                        )
                    }
                ],
                max_tokens=150,
                temperature=0.6
            )
            bio = response.choices[0].message.content.strip()
            
            # Validar que la bio no esté vacía
            if not bio or len(bio) < 10:
                return f"{player_name} es un futbolista profesional con destacada trayectoria internacional."
            
            return bio
            
        except Exception as e:
            # Fallback si OpenAI falla
            return f"{player_name} es un futbolista profesional con destacada trayectoria internacional."
    
    def _generate_ai_fallback(
        self, 
        name: str, 
        season: Optional[int], 
        nationality: Optional[str]
    ) -> Dict[str, Any]:
        """Genera jugador ficticio con IA (SIEMPRE incluye bio)"""
        prompt = (
            f"Genera un JSON con estadísticas de {name}. "
            f"Si existe, usa datos reales; si no, invéntalo coherentemente.\n\n"
            f"FORMATO:\n"
            f"{{\n"
            f"  \"jugador\": {{\"id\": <num>, \"nombre\": \"<n>\", \"nacionalidad\": \"<país>\", \"edad\": <num>, \"foto\": \"<url>\"}},\n"
            f"  \"temporada\": \"{season or '2024/2025'}\",\n"
            f"  \"goles\": <num>, \"asistencias\": <num>, \"partidos\": <num>, \"minutos\": <num>, \"rating\": <num>,\n"
            f"  \"equipos\": [{{\"nombre\": \"<equipo>\", \"liga\": \"<liga>\"}}],\n"
            f"  \"bio\": \"<biografía de máximo 5 líneas sobre el jugador>\"\n"
            f"}}\n\n"
            f"IMPORTANTE: La bio debe incluir nacionalidad, posición, estilo de juego y un logro destacado.\n"
            f"Solo JSON, sin texto extra."
        )
        
        try:
            response = self.openai_client.chat.completions.create(
                model=self.settings.OPENAI_MODEL_ID,
                messages=[
                    {"role": "system", "content": "Responde únicamente JSON válido con todos los campos requeridos."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=500,  # Aumentado para incluir bio
                temperature=0.2
            )
            
            content = response.choices[0].message.content.strip()
            if content.startswith("```"):
                content = content.replace("```json", "").replace("```", "").strip()
            
            parsed = json.loads(content)
            
            # ✅ Validar que tenga bio, si no, agregarla
            if "bio" not in parsed or not parsed["bio"]:
                parsed["bio"] = self._generate_quick_bio(name)
            
            return parsed
            
        except Exception as e:
            # ✅ Fallback FINAL con bio incluida
            bio = self._generate_quick_bio(name)
            
            return {
                "jugador": {
                    "id": random.randint(100000, 999999),
                    "nombre": name,
                    "nacionalidad": nationality or "Desconocida",
                    "edad": random.randint(18, 34),
                    "foto": "https://media.api-sports.io/football/players/default.png"
                },
                "temporada": season or "2024/2025",
                "goles": random.randint(0, 20),
                "asistencias": random.randint(0, 12),
                "partidos": random.randint(5, 38),
                "minutos": random.randint(300, 3200),
                "rating": round(random.uniform(6.0, 7.9), 2),
                "equipos": [{"nombre": "Club Desconocido", "liga": "Liga Desconocida"}],
                "bio": bio  # ✅ Siempre incluye bio
            }