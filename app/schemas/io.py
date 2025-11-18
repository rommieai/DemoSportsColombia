from __future__ import annotations 
from pydantic import BaseModel
from typing import List, Optional, Dict, Any

class FacePrediction(BaseModel):
    bbox: List[int]  # [top, right, bottom, left]
    label: str
    score: float

class JerseyDetection(BaseModel):
    team: str
    bbox: List[int]  # [x1,y1,x2,y2]
    confidence: float

class CompleteAnalysisResponse(BaseModel):
    """Respuesta del análisis completo con caras + camisetas + tiempo"""
    num_faces: int
    faces: List[FacePrediction]
    jerseys: List[JerseyDetection]
    colombia_count: int  # Número de camisetas de Colombia detectadas
    match_time: Optional[str]  # Tiempo del partido en formato "M:SS" o "MM:SS"
    image_processed: bool
    total_detections: int
    processing_times: Dict[str, float]  # Tiempos de cada componente

class TimeOnlyResponse(BaseModel):
    """Respuesta del análisis solo de tiempo"""
    match_time: Optional[str]  # Tiempo del partido en formato "M:SS" o "MM:SS"
    detected: bool  # True si se detectó, False si no
    processing_time: float  # Tiempo de procesamiento en segundos

class CachedAnalysisResponse(BaseModel):
    """Respuesta cuando se usa caché"""
    source: str  # "cache" o "new_analysis"
    match_time: str
    num_faces: int
    faces: List[FacePrediction]
    jerseys: List[JerseyDetection]
    colombia_count: int  # Número de camisetas de Colombia detectadas
    image_processed: bool
    total_detections: int
    processing_times: Optional[Dict[str, float]] = None  # Solo si es análisis nuevo

class CacheStatsResponse(BaseModel):
    """Respuesta con estadísticas del caché"""
    size: int
    max_size: int
    usage_percent: float
    times_cached: List[str]
    oldest_time: Optional[str]
    newest_time: Optional[str]

class AskPayload(BaseModel):
    prompt: str
    lang: Optional[str] = "es"