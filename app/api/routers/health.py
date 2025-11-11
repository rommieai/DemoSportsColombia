from fastapi import APIRouter
from app.api.deps import analysis_service

router = APIRouter(tags=["health"])

@router.get("/health")
def health():
    svc = analysis_service()
    return {
        "status": "ok",
        "models": {
            "face_recognition": svc.face_rec.loaded,
            "yolo_world": svc.jersey_det.yolo is not None,
        },
        "capabilities": {
            "face_detection": True,
            "face_recognition": svc.face_rec.loaded,
            "jersey_detection_yolo": svc.jersey_det.yolo is not None,
            "jersey_detection_colors": True,
        }
    }
