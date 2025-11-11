from functools import lru_cache
from app.core.config import get_settings
from app.ml.faces.recognizer import FaceRecognizer
from app.ml.classifiers.goal_clip_keras import GoalNoGoalClassifier
from app.ml.detectors.jerseys import JerseyDetector
from app.services.analysis_service import AnalysisService
from app.services.match_events_service import MatchEventsService, MatchValidator

@lru_cache
def analysis_service() -> AnalysisService:
    """Servicio principal de análisis (ML)"""
    s = get_settings()
    face = FaceRecognizer(
        s.MLP_MODEL_PATH, s.SCALER_PATH, s.LABELS_JSON, pca_path=s.PCA_PATH
    )
    goal = GoalNoGoalClassifier(s.GOAL_MODEL_PATH, s.GOAL_LABELS_PATH)
    jersey = JerseyDetector()
    return AnalysisService(face, goal, jersey)


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