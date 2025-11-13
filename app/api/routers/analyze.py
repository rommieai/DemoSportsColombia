from fastapi import APIRouter, UploadFile, File, HTTPException
from PIL import Image
import io, time
from app.services.analysis_service import AnalysisService
from app.schemas.io import CompleteResponse

router = APIRouter(tags=["analyze"])

def get_service() -> AnalysisService:
    # Podrías inyectar por deps y vida-útil global
    from app.api.deps import analysis_service
    return analysis_service()

@router.post("/analyze", response_model=CompleteResponse)
async def analyze_image(file: UploadFile = File(...)):
    try:
        t0 = time.perf_counter()
        img = Image.open(io.BytesIO(await file.read()))
        resp = get_service().analyze(img)
        print(f"analyze ms={(time.perf_counter()-t0)*1000:.2f}")
        return resp
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error procesando imagen: {e}")