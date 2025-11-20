"""Servicio para generación de trivia deportiva"""
import json
from typing import List, Dict, Any
from openai import OpenAI
from app.core.config import get_settings
from app.core.cache import trivia_cache


class TriviaService:
    """Servicio para generar preguntas de trivia sobre equipos"""
    
    def __init__(self):
        settings = get_settings()
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
    
    async def generate_trivia(
        self,
        team1: str,
        team2: str,
        num_questions: int = 10
    ) -> Dict[str, Any]:
        """
        Genera preguntas de trivia para dos equipos.
        
        Args:
            team1: Nombre del primer equipo
            team2: Nombre del segundo equipo
            num_questions: Número de preguntas a generar (default: 10)
            
        Returns:
            Dict con: team1, team2, questions, from_cache
        """
        # Verificar cache
        cached_trivia = trivia_cache.get(team1, team2)
        if cached_trivia:
            return {
                "team1": team1,
                "team2": team2,
                "questions": cached_trivia,
                "from_cache": True
            }
        
        # Generar preguntas alternando equipos
        questions = []
        for i in range(num_questions):
            current_team = team1 if i % 2 == 0 else team2
            question = await self._generate_single_question(current_team)
            questions.append(question)
        
        # Guardar en cache
        trivia_cache.set(team1, team2, questions)
        
        return {
            "team1": team1,
            "team2": team2,
            "questions": questions,
            "from_cache": False
        }
    
    async def _generate_single_question(self, team: str) -> Dict[str, Any]:
        """
        Genera una única pregunta de trivia para un equipo.
        
        Args:
            team: Nombre del equipo
            
        Returns:
            Dict con: question (str), answer (bool)
        """
        prompt = self._build_trivia_prompt(team)
        
        response = self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        
        raw_content = response.choices[0].message.content.strip()
        
        # Intentar parsear JSON
        try:
            data = json.loads(raw_content)
            # Validar estructura
            if "question" not in data or "answer" not in data:
                raise ValueError("JSON inválido")
            return data
        except (json.JSONDecodeError, ValueError):
            # Fallback si el JSON es inválido
            return {
                "question": raw_content.replace("\n", " "),
                "answer": True
            }
    
    def _build_trivia_prompt(self, team: str) -> str:
        """Construye el prompt para generar una pregunta de trivia"""
        return f"""
Genera UNA sola pregunta de trivia sobre datos curiosos del equipo {team}.

Formato estricto JSON:
{{"question": "texto de la pregunta", "answer": true/false}}

Reglas:
1. La pregunta debe ser sobre hechos verificables (títulos, jugadores históricos, récords, etc.)
2. Debe ser de verdadero/falso
3. Debe ser interesante y no obvia
4. Solo devuelve el JSON, sin texto adicional

Ejemplo:
{{"question": "El {team} ha ganado más de 5 títulos de liga en su historia", "answer": true}}
"""