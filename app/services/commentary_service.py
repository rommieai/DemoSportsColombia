"""Servicio para generación de comentarios con IA - OPTIMIZADO CON FIREBASE"""
from typing import Optional, Dict, Any, List
import openai
import hashlib
from app.core.config import get_settings
from app.services.firebase_service import firebase_service


class CommentaryService:
    """Servicio para generar comentarios deportivos con IA"""
    
    # Colecciones de Firebase para cache
    COLLECTION_COMMENTS = "ai_comments"
    COLLECTION_COMMENT_HISTORY = "comment_history"
    
    def __init__(self):
        settings = get_settings()
        openai.api_key = settings.OPENAI_API_KEY
        self.fb = firebase_service
    
    async def generate_commentary(
        self,
        match_id: int,
        match_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Genera un comentario para un partido.
        
        OPTIMIZADO: Usa Firebase para persistir cache y historial
        
        Args:
            match_id: ID del partido
            match_data: Datos completos del partido
            
        Returns:
            Dict con: minute, commentary, from_cache
        """
        # 1. Verificar cache de comentarios en Firebase
        comment_doc_id = f"comment_{match_id}"
        cached_comment = self.fb.get_if_valid(
            self.COLLECTION_COMMENTS, 
            comment_doc_id
        )
        
        if cached_comment:
            return {
                "minute": match_data.get("minuto"),
                "commentary": cached_comment["text"],
                "from_cache": True
            }
        
        # 2. Obtener historial de comentarios previos desde Firebase
        history_doc_id = f"history_{match_id}"
        history_data = self.fb.get_if_valid(
            self.COLLECTION_COMMENT_HISTORY, 
            history_doc_id
        )
        
        previous_commentaries = history_data.get("commentaries", []) if history_data else []
        
        # 3. Construir prompt con historial
        prompt = self._build_commentary_prompt(
            match_data=match_data,
            previous_commentaries=previous_commentaries
        )
        
        # 4. Llamar a OpenAI
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.8
        )
        
        commentary = response.choices[0].message.content.strip()
        
        # 5. Evitar repetición exacta con hash
        current_hash = hashlib.md5(commentary.encode()).hexdigest()
        last_hash = history_data.get("last_hash") if history_data else None
        
        if current_hash == last_hash:
            commentary = "Continúa el partido sin novedades importantes."
            current_hash = hashlib.md5(commentary.encode()).hexdigest()
        
        # 6. Guardar comentario en cache de Firebase (TTL 30 segundos)
        self.fb.set_with_ttl(
            self.COLLECTION_COMMENTS,
            comment_doc_id,
            {"text": commentary, "hash": current_hash},
            30  # 30 segundos para evitar spam
        )
        
        # 7. Actualizar historial en Firebase
        new_commentaries = previous_commentaries[-9:] + [commentary]  # Últimos 10
        self.fb.set_with_ttl(
            self.COLLECTION_COMMENT_HISTORY,
            history_doc_id,
            {
                "commentaries": new_commentaries,
                "last_hash": current_hash
            },
            3600  # 1 hora de historial
        )
        
        return {
            "minute": match_data.get("minuto"),
            "commentary": commentary,
            "from_cache": False
        }
    
    def _build_commentary_prompt(
        self,
        match_data: Dict[str, Any],
        previous_commentaries: List[str]
    ) -> str:
        """Construye el prompt para el modelo de IA con historial"""
        
        # Formatear comentarios previos
        history_text = ""
        if previous_commentaries:
            history_text = "\n\nCOMENTARIOS PREVIOS QUE YA DIJISTE (NO REPITAS ESTOS):\n"
            for i, comment in enumerate(previous_commentaries[-5:], 1):
                history_text += f"{i}. {comment}\n"
        
        return f"""
Eres un comentarista deportivo profesional y creativo.
Genera **una frase corta y precisa** sobre el partido actual (máximo 10 palabras).

IMPORTANTE: 
- Sé ORIGINAL y VARIADO en tus comentarios
- NO repitas frases o conceptos que ya usaste anteriormente
- Si no hay eventos nuevos, busca ángulos diferentes: estadísticas, jugadores clave, análisis táctico, contexto de la liga, etc.
- Varía tu enfoque: a veces habla del juego, a veces de estadísticas, a veces del contexto{history_text}

Datos del partido:
- Liga: {match_data.get('liga')}
- Equipos: {match_data.get('equipos')}
- Marcador: {match_data.get('marcador')}
- Minuto: {match_data.get('minuto')}
- Estado: {match_data.get('estado')}
- Eventos recientes: {match_data.get('eventos', [])[-3:]}  # Últimos 3 eventos

Genera UN SOLO comentario original y diferente a los anteriores.
"""
    
    async def answer_question(
        self,
        match_id: int,
        question: str,
        match_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Responde preguntas sobre un partido específico.
        
        OPTIMIZADO: Cache de respuestas en Firebase
        
        Args:
            match_id: ID del partido
            question: Pregunta del usuario
            match_data: Datos del partido
            
        Returns:
            Dict con: answer, match_context_used
        """
        # 1. Crear clave de cache basada en pregunta
        question_hash = hashlib.md5(question.lower().encode()).hexdigest()[:8]
        cache_key = f"answer_{match_id}_{question_hash}"
        
        # 2. Verificar cache
        cached_answer = self.fb.get_if_valid(
            self.COLLECTION_COMMENTS,
            cache_key
        )
        
        if cached_answer:
            return {
                "answer": cached_answer["answer"],
                "match_context_used": True,
                "from_cache": True
            }
        
        # 3. Si no hay match_data, obtenerlo desde Firebase
        if not match_data:
            from app.tasks import get_match_data_from_firebase
            match_data = get_match_data_from_firebase(match_id)
        
        if not match_data:
            return {
                "error": "No se pudo obtener información del partido.",
                "match_context_used": False
            }
        
        # 4. Generar respuesta
        prompt = f"""
Actúa como un comentarista deportivo profesional.
Usa exclusivamente la información de este partido para responder.

Información del partido:
{match_data}

Pregunta del usuario: {question}

Responde de forma clara, emocionante y precisa. Las respuestas no pueden tener más de 50 palabras o 240 caracteres. Retorna la respuesta en formato HTML.
"""
        
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        
        answer = response.choices[0].message.content
        
        # 5. Guardar en cache (5 minutos - las respuestas pueden reutilizarse)
        self.fb.set_with_ttl(
            self.COLLECTION_COMMENTS,
            cache_key,
            {"answer": answer},
            300  # 5 minutos
        )
        
        return {
            "answer": answer,
            "match_context_used": True,
            "from_cache": False
        }
    
    def clear_match_history(self, match_id: int):
        """Limpia el historial de comentarios de un partido"""
        history_doc_id = f"history_{match_id}"
        self.fb.delete(self.COLLECTION_COMMENT_HISTORY, history_doc_id)
        print(f"✓ Historial de comentarios limpiado para partido {match_id}")