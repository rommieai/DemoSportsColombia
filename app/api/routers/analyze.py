"""Router de análisis con procesamiento paralelo y caché inteligente - Actualizado para Colombia"""
from fastapi import APIRouter, UploadFile, File, HTTPException
from PIL import Image
import io
import time
import logging

from app.services.analysis_service import AnalysisService
from app.services.cache_service import AnalysisCacheService
from app.schemas.io import (
    CompleteAnalysisResponse, 
    TimeOnlyResponse, 
    CachedAnalysisResponse,
    CacheStatsResponse
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["analyze"])


def get_service() -> AnalysisService:
    """Obtiene el servicio de análisis"""
    from app.api.deps import analysis_service
    return analysis_service()


def get_cache() -> AnalysisCacheService:
    """Obtiene el servicio de caché"""
    from app.api.deps import cache_service
    return cache_service()


@router.post("/analyze-complete", response_model=CompleteAnalysisResponse)
async def analyze_complete(file: UploadFile = File(...)):
    """
    Análisis completo con procesamiento paralelo: caras + camisetas de Colombia + tiempo (OCR)
    
    - Procesa caras, camisetas y tiempo del partido en paralelo
    - Guarda el resultado en caché indexado por tiempo del partido
    - Si el caché está lleno (50 elementos), elimina el más viejo
    
    **Procesamiento paralelo:**
    - Thread 1: Detección y reconocimiento de caras
    - Thread 2: Detección de camisetas amarillas de Colombia (YOLO + colores)
    - Thread 3: OCR del tiempo del partido (EasyOCR)
    
    **Ejemplo de uso:**
    ```bash
    curl -X POST "http://localhost:8003/analyze-complete" \\
         -F "file=@imagen.jpg"
    ```
    """
    try:
        t0 = time.perf_counter()
        
        # Cargar imagen
        img_bytes = await file.read()
        img = Image.open(io.BytesIO(img_bytes))
        
        # Análisis completo con procesamiento paralelo
        service = get_service()
        result = service.analyze_complete(img)
        
        # Si se detectó tiempo, guardar en caché
        if result.match_time:
            cache = get_cache()
            
            # Preparar datos para caché (sin processing_times para ahorrar memoria)
            cache_data = {
                "num_faces": result.num_faces,
                "faces": [f.model_dump() for f in result.faces],
                "jerseys": [j.model_dump() for j in result.jerseys],
                "colombia_count": result.colombia_count,
                "total_detections": result.total_detections,
                "image_processed": True
            }
            
            cache.set(result.match_time, cache_data)
            logger.info(f"✓ Resultado guardado en caché para tiempo: {result.match_time}")
        
        total_time = time.perf_counter() - t0
        logger.info(f"✓ /analyze-complete completado en {total_time:.3f}s")
        
        return result
        
    except Exception as e:
        logger.error(f"✗ Error en /analyze-complete: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500, 
            detail=f"Error procesando imagen: {str(e)}"
        )


@router.post("/analyze-time", response_model=CachedAnalysisResponse)
async def analyze_time(file: UploadFile = File(...)):
    """
    Análisis inteligente con caché:
    1. Detecta solo el tiempo del partido (OCR rápido)
    2. Si el tiempo existe en caché, devuelve resultados almacenados
    3. Si no existe, hace análisis completo y guarda en caché
    
    **Ventaja:** Evita procesamiento redundante de frames similares
    
    **Flujo:**
    ```
    Imagen → OCR (rápido) → ¿Tiempo en caché?
                           ├─ SÍ → Devolver de caché (instantáneo)
                           └─ NO → Análisis completo + guardar caché
    ```
    
    **Ejemplo de uso:**
    ```bash
    curl -X POST "http://localhost:8003/analyze-time" \\
         -F "file=@imagen.jpg"
    ```
    """
    try:
        t0 = time.perf_counter()
        
        # Cargar imagen
        img_bytes = await file.read()
        img = Image.open(io.BytesIO(img_bytes))
        
        # Paso 1: Detectar solo el tiempo (rápido)
        service = get_service()
        time_result = service.analyze_time_only(img)
        
        if not time_result.detected or time_result.match_time is None:
            logger.warning("✗ No se detectó tiempo en la imagen")
            raise HTTPException(
                status_code=404,
                detail="No se pudo detectar el tiempo del partido en la imagen"
            )
        
        match_time = time_result.match_time
        cache = get_cache()
        
        # Paso 2: Verificar si existe en caché
        cached_result = cache.get(match_time)
        
        if cached_result:
            # ¡Hit de caché! Devolver resultado almacenado
            total_time = time.perf_counter() - t0
            logger.info(f"✓ [CACHE HIT] Tiempo {match_time} encontrado. "
                       f"Respuesta en {total_time:.3f}s")
            
            return CachedAnalysisResponse(
                source="cache",
                match_time=match_time,
                num_faces=cached_result["num_faces"],
                faces=cached_result["faces"],
                jerseys=cached_result["jerseys"],
                colombia_count=cached_result["colombia_count"],
                image_processed=cached_result["image_processed"],
                total_detections=cached_result["total_detections"],
                processing_times=None  # No disponible desde caché
            )
        
        # Paso 3: No existe en caché, hacer análisis completo
        logger.info(f"✓ [CACHE MISS] Tiempo {match_time} no encontrado. "
                   f"Realizando análisis completo...")
        
        # Recrear imagen desde bytes (ya fue leída)
        img = Image.open(io.BytesIO(img_bytes))
        complete_result = service.analyze_complete(img)
        
        # Verificar que coincidan los tiempos (deberían)
        if complete_result.match_time != match_time:
            logger.warning(f"⚠ Tiempos no coinciden: {match_time} vs {complete_result.match_time}")
        
        # Guardar en caché
        cache_data = {
            "num_faces": complete_result.num_faces,
            "faces": [f.model_dump() for f in complete_result.faces],
            "jerseys": [j.model_dump() for j in complete_result.jerseys],
            "colombia_count": complete_result.colombia_count,
            "total_detections": complete_result.total_detections,
            "image_processed": True
        }
        cache.set(match_time, cache_data)
        
        total_time = time.perf_counter() - t0
        logger.info(f"✓ /analyze-time completado en {total_time:.3f}s")
        
        return CachedAnalysisResponse(
            source="new_analysis",
            match_time=match_time,
            num_faces=complete_result.num_faces,
            faces=complete_result.faces,
            jerseys=complete_result.jerseys,
            colombia_count=complete_result.colombia_count,
            image_processed=complete_result.image_processed,
            total_detections=complete_result.total_detections,
            processing_times=complete_result.processing_times
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"✗ Error en /analyze-time: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"Error procesando imagen: {str(e)}"
        )


@router.get("/cache/stats", response_model=CacheStatsResponse)
async def get_cache_stats():
    """
    Obtiene estadísticas del caché de análisis
    
    **Información incluida:**
    - Tamaño actual y máximo
    - Porcentaje de uso
    - Lista de tiempos almacenados
    - Tiempo más viejo y más nuevo
    
    **Ejemplo:**
    ```bash
    curl "http://localhost:8003/cache/stats"
    ```
    """
    try:
        cache = get_cache()
        stats = cache.get_stats()
        return CacheStatsResponse(**stats)
    except Exception as e:
        logger.error(f"✗ Error obteniendo estadísticas de caché: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error obteniendo estadísticas: {str(e)}"
        )


@router.post("/cache/clear")
async def clear_cache():
    """
    Limpia todo el caché de análisis
    
    **Uso:** Para reiniciar el sistema de caché o liberar memoria
    
    **Ejemplo:**
    ```bash
    curl -X POST "http://localhost:8003/cache/clear"
    ```
    """
    try:
        cache = get_cache()
        old_size = len(cache.get_all_times())
        cache.clear()
        
        return {
            "message": "Caché limpiado exitosamente",
            "elements_removed": old_size
        }
    except Exception as e:
        logger.error(f"✗ Error limpiando caché: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error limpiando caché: {str(e)}"
        )


@router.delete("/cache/time/{match_time}")
async def remove_time_from_cache(match_time: str):
    """
    Elimina un tiempo específico del caché
    
    **Parámetros:**
    - match_time: Tiempo en formato "M:SS" o "MM:SS"
    
    **Ejemplo:**
    ```bash
    curl -X DELETE "http://localhost:8003/cache/time/45:30"
    ```
    """
    try:
        cache = get_cache()
        removed = cache.remove(match_time)
        
        if removed:
            return {
                "message": f"Tiempo {match_time} eliminado del caché",
                "removed": True
            }
        else:
            raise HTTPException(
                status_code=404,
                detail=f"Tiempo {match_time} no encontrado en caché"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"✗ Error eliminando tiempo del caché: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error eliminando del caché: {str(e)}"
        )