"""Servicio para generación de comentarios con IA"""
from typing import Optional, Dict, Any, List
import openai
import hashlib
from app.core.config import get_settings
from app.core.cache import comment_cache, match_data_cache, events_history


class CommentaryService:
    """Servicio para generar comentarios deportivos con IA"""
    
    def __init__(self):
        settings = get_settings()
        openai.api_key = settings.OPENAI_API_KEY
    
    async def generate_commentary(
        self,
        match_id: int,
        match_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Genera un comentario para un partido.
        
        Args:
            match_id: ID del partido
            match_data: Datos completos del partido
            
        Returns:
            Dict con: minute, commentary, from_cache
        """
        # Verificar cache
        cached_comment = comment_cache.get(match_id)
        if cached_comment:
            return {
                "minute": match_data.get("minuto"),
                "commentary": cached_comment,
                "from_cache": True
            }
        
        # Obtener eventos previos y actuales
        previous_events = events_history.get_last_events(match_id) or []
        current_events = match_data.get("eventos", [])
        
        # Actualizar historial
        events_history.set_last_events(match_id, current_events)
        
        # Generar prompt
        prompt = self._build_commentary_prompt(
            match_data=match_data,
            previous_events=previous_events,
            current_events=current_events
        )
        
        # Llamar a OpenAI
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        
        commentary = response.choices[0].message.content.strip()
        
        # Evitar repetición exacta
        last_hash = comment_cache.get_last_hash(match_id)
        current_hash = hashlib.md5(commentary.encode()).hexdigest()
        
        if current_hash == last_hash:
            commentary = "Continúa el partido sin novedades importantes."
        
        # Guardar en cache
        comment_cache.set(match_id, commentary)
        
        return {
            "minute": match_data.get("minuto"),
            "commentary": commentary,
            "from_cache": False
        }
    
    def _build_commentary_prompt(
        self,
        match_data: Dict[str, Any],
        previous_events: List[Dict],
        current_events: List[Dict]
    ) -> str:
        """Construye el prompt para el modelo de IA"""
        return f"""
Eres un comentarista deportivo profesional.
Genera **una frase corta y precisa** sobre el partido actual (máximo 10 palabras).

Si hubo cambios respecto al minuto anterior, destácalos.
Si no hubo cambios, genera un comentario relevante usando estadísticas, alineaciones o información de la liga.

Datos previos:
{previous_events}

Datos actuales:
{current_events}

Datos adicionales del partido:
- Liga: {match_data.get('liga')}
- Equipos: {match_data.get('equipos')}
- Marcador: {match_data.get('marcador')}
- Minuto: {match_data.get('minuto')}
- Estadísticas: {match_data.get('estadisticas', {})}
- Lineups disponibles: {match_data.get('lineups_disponibles', False)}
"""
    
    async def answer_question(
        self,
        match_id: int,
        question: str,
        match_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Responde preguntas sobre un partido específico.
        
        Args:
            match_id: ID del partido
            question: Pregunta del usuario
            match_data: Datos del partido (opcional, se obtiene del cache si no se provee)
            
        Returns:
            Dict con: answer, match_context_used
        """
        if not match_data:
            match_data = match_data_cache.get(match_id)
        
        if not match_data:
            return {
                "error": "No se pudo obtener información del partido.",
                "match_context_used": False
            }
        
        prompt = f"""
Actúa como un comentarista deportivo profesional.
Usa exclusivamente la información de este partido para responder.

Información del partido:
{match_data}

Pregunta del usuario: {question}

Responde de forma clara, emocionante y precisa. Las respuestas no pueden tener más de 70 palabras.
"""
        
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        
        return {
            "answer": response.choices[0].message.content,
            "match_context_used": True
        }