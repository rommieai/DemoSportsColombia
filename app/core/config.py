# app/core/config.py
from functools import lru_cache
from pathlib import Path
from typing import Optional, List
import os

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[1]

class Settings(BaseSettings):
    # === Artefactos de FaceNet + MLP PyTorch ===
    ARTIFACT_DIR: str = str(BASE_DIR / "artifacts" / "facenet_mlp")
    
    # Modelo PyTorch (MLP classifier)
    MLP_MODEL_PATH: str = "{}/model.pt"
    
    # Scaler y PCA (sklearn)
    SCALER_PATH: str = "{}/scaler.joblib"
    PCA_PATH: str = "{}/pca.joblib"
    
    # Labels
    LABELS_JSON: str = "{}/label_encoder.json"

    # === Modelos de visión ===
    MODELS_DIR: str = str(BASE_DIR / "models")
    YOLO_WORLD_S_PATH: str = "{}/yolov8s-worldv2.pt"
    YOLO_WORLD_L_PATH: str = "{}/yolov8l-worldv2.pt"

    # === Configuración de OCR ===
    USE_GPU_OCR: bool = os.getenv("USE_GPU_OCR", "false").lower() == "true"
    
    # === Configuración de Caché ===
    CACHE_MAX_SIZE: int = int(os.getenv("CACHE_MAX_SIZE", "50"))

    # === API Externa de Eventos del Partido ===
    MATCH_EVENTS_API_URL: str = os.getenv(
        "MATCH_EVENTS_API_URL", 
        "https://api.example.com/v1"
    )
    MATCH_EVENTS_API_KEY: Optional[str] = os.getenv("MATCH_EVENTS_API_KEY")
    
    # ID del partido por defecto (Qatar 2022 Final)
    DEFAULT_MATCH_ID: str = os.getenv("DEFAULT_MATCH_ID", "worldcup-2022-final")

    # === OpenAI / CORS ===
    OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")
    OPENAI_MODEL_ID: str = os.getenv("MODEL_ID", "gpt-4.1-mini")
    CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://demo-world-cup-ts.kontent-dev.com",
    ]
    
    # === API de fútbol ===
    FOOTBALL_API_KEY: str = "0e88fe12ff5324e08d0dd7b35659829e"
    
    # Configuración de pydantic v2
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore",
    )

@lru_cache
def get_settings() -> Settings:
    s = Settings()
    # Formatear paths con el directorio de artefactos
    s.MLP_MODEL_PATH = s.MLP_MODEL_PATH.format(s.ARTIFACT_DIR)
    s.SCALER_PATH = s.SCALER_PATH.format(s.ARTIFACT_DIR)
    s.PCA_PATH = s.PCA_PATH.format(s.ARTIFACT_DIR)
    s.LABELS_JSON = s.LABELS_JSON.format(s.ARTIFACT_DIR)
    
    # Formatear paths de modelos de visión
    s.YOLO_WORLD_S_PATH = s.YOLO_WORLD_S_PATH.format(s.MODELS_DIR)
    s.YOLO_WORLD_L_PATH = s.YOLO_WORLD_L_PATH.format(s.MODELS_DIR)
    
    return s
