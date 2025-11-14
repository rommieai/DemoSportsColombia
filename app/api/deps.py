from functools import lru_cache
from app.core.config import get_settings
from app.ml.faces.recognizer import FaceRecognizer
from app.ml.detectors.jerseys import JerseyDetector
from app.ml.detectors.time_ocr import TimeOCRDetector
from app.services.analysis_service import AnalysisService
from app.services.cache_service import AnalysisCacheService
from app.services.match_events_service import MatchEventsService, MatchValidator

@lru_cache
def analysis_service() -> AnalysisService:
    """Servicio principal de análisis (ML) con procesamiento paralelo"""
    s = get_settings()
    
    # Componentes de ML
    face = FaceRecognizer(
        s.MLP_MODEL_PATH, s.SCALER_PATH, s.LABELS_JSON, pca_path=s.PCA_PATH
    )
    jersey = JerseyDetector()
    time_ocr = TimeOCRDetector(gpu=s.USE_GPU_OCR)
    
    # Servicio con procesamiento paralelo (3 workers: caras, camisetas, tiempo)
    return AnalysisService(face, jersey, time_ocr, max_workers=3)


@lru_cache
def cache_service() -> AnalysisCacheService:
    """Servicio de caché para resultados de análisis"""
    s = get_settings()
    return AnalysisCacheService(max_size=s.CACHE_MAX_SIZE)


@lru_cache
def match_events_service() -> MatchEventsService:
    """Servicio de conexión con API externa de eventos"""
    s = get_settings()
    return MatchEventsService(
        api_url=s.MATCH_EVENTS_API_URL,
        api_key=s.MATCH_EVENTS_API_KEY
    )


@lru_cache
def match_validator() -> MatchValidator:
    """Validador de eventos (combina ML + API externa)"""
    events_service = match_events_service()
    return MatchValidator(events_service)
