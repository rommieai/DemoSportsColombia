"""
Endpoints para validación de eventos contra API externa
"""
from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel
from typing import Optional
from PIL import Image
import io
import time

from app.api.deps import analysis_service, match_validator
from app.schemas.io import CompleteAnalysisResponse

router = APIRouter(tags=["validate"])


class ValidateRequest(BaseModel):
    match_id: str
    event_type: Optional[str] = "goal"  # goal, corner, foul, etc.
    team: Optional[str] = None


class ValidatedAnalysisResponse(BaseModel):
    """Respuesta del análisis con validación de eventos"""
    # Datos del análisis normal
    analysis: CompleteAnalysisResponse
    
    # Validación contra eventos reales
    validation: dict
    
    # Metadatos
    is_live_event: bool
    is_replay: bool
    confidence_score: float


@router.post("/validate/analyze", response_model=ValidatedAnalysisResponse)
async def analyze_and_validate(
    match_id: str,
    file: UploadFile = File(...)
):
    """
    Analiza la imagen Y valida contra eventos reales del partido
    
    - Detecta caras, goles y camisetas
    - Consulta API externa de eventos del partido
    - Valida si el gol detectado es real o repetición
    """
    try:
        t0 = time.perf_counter()
        
        # 1. Análisis normal de la imagen
        img = Image.open(io.BytesIO(await file.read()))
        analysis_result = analysis_service().analyze(img)
        
        # 2. Validar contra eventos reales
        validator = match_validator()
        
        # Detectar si es un gol
        top_event = analysis_result.top_event.event_class.lower()
        
        if "goal" in top_event:
            # Validar gol detectado
            validation = await validator.validate_goal_detection(match_id)
        else:
            # Validar otro tipo de evento
            validation = await validator.validate_event_detection(
                match_id, 
                event_type=top_event
            )
        
        # 3. Calcular confianza combinada
        model_confidence = analysis_result.top_event.confidence
        temporal_confidence = validation.get("confidence", 0.5)
        
        # Confianza combinada (80% modelo, 20% validación temporal)
        combined_confidence = (model_confidence * 0.8) + (temporal_confidence * 0.2)
        
        print(f"Análisis + validación: {(time.perf_counter()-t0)*1000:.2f}ms")
        
        return ValidatedAnalysisResponse(
            analysis=analysis_result,
            validation=validation,
            is_live_event=validation.get("is_valid", False),
            is_replay=validation.get("is_replay", False),
            confidence_score=combined_confidence
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Error en análisis validado: {e}"
        )


@router.get("/validate/match/{match_id}/status")
async def get_match_status(match_id: str):
    """
    Obtiene el estado actual del partido desde la API externa
    """
    try:
        validator = match_validator()
        state = await validator.events_service.get_current_match_state(match_id)
        return state
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/validate/match/{match_id}/events")
async def get_match_events(match_id: str, last_minutes: int = 5):
    """
    Obtiene eventos recientes del partido
    """
    try:
        validator = match_validator()
        events = await validator.events_service.get_recent_events(match_id, last_minutes)
        
        return {
            "match_id": match_id,
            "events": [
                {
                    "type": e.event_type,
                    "minute": e.minute,
                    "team": e.team,
                    "player": e.player,
                    "timestamp": e.timestamp.isoformat()
                }
                for e in events
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/validate/check-goal")
async def check_goal_validity(request: ValidateRequest):
    """
    Verifica si un gol detectado es válido (sin necesidad de imagen)
    Útil para verificación rápida
    """
    try:
        validator = match_validator()
        validation = await validator.validate_goal_detection(
            request.match_id,
            detected_team=request.team
        )
        return validation
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))