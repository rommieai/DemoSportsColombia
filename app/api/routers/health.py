from fastapi import APIRouter
from app.api.deps import analysis_service, cache_service

router = APIRouter(tags=["health"])

@router.get("/health")
def health():
    """
    Health check con información de modelos y servicios
    
    **Información incluida:**
    - Estado de los modelos ML
    - Capacidades disponibles
    - Estado del caché
    """
    try:
        svc = analysis_service()
        cache = cache_service()
        cache_stats = cache.get_stats()
        
        return {
            "status": "ok",
            "models": {
                "face_recognition": svc.face_rec.loaded,
                "yolo_world": svc.jersey_det.yolo is not None,
                "time_ocr": svc.time_det.reader is not None,
            },
            "capabilities": {
                "face_detection": True,
                "face_recognition": svc.face_rec.loaded,
                "jersey_detection_yolo": svc.jersey_det.yolo is not None,
                "jersey_detection_colors": True,
                "time_detection_ocr": svc.time_det.reader is not None,
                "parallel_processing": True,
            },
            "cache": {
                "enabled": True,
                "size": cache_stats["size"],
                "max_size": cache_stats["max_size"],
                "usage_percent": cache_stats["usage_percent"]
            },
            "processing": {
                "parallel_workers": 3,
                "components": ["faces", "jerseys", "time_ocr"]
            }
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }
