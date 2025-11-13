from __future__ import annotations 
from pydantic import BaseModel
from typing import List, Optional

class FacePrediction(BaseModel):
    bbox: List[int]  # [top, right, bottom, left]
    label: str
    score: float

class JerseyDetection(BaseModel):
    team: str
    bbox: List[int]  # [x1,y1,x2,y2]
    confidence: float

class EventPrediction(BaseModel):
    event_class: str
    confidence: float
    percentage: float

class CompleteResponse(BaseModel):
    num_faces: int
    faces: List[FacePrediction]
    event_predictions: List[EventPrediction]
    top_event: EventPrediction
    jerseys: List[JerseyDetection]  # CORREGIDO: era List[dict], ahora es List[JerseyDetection]
    argentina_count: int
    france_count: int
    image_processed: bool
    total_detections: int

class AskPayload(BaseModel):
    prompt: str
    lang: Optional[str] = "es"