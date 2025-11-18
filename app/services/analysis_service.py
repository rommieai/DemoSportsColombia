"""Servicio de análisis con procesamiento paralelo - ACTUALIZADO para Colombia"""
from __future__ import annotations

from typing import List, Dict, Any, Optional
import mediapipe as mp
import numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import logging

from app.ml.faces.recognizer import FaceRecognizer
from app.ml.detectors.jerseys import JerseyDetector
from app.ml.detectors.time_ocr import TimeOCRDetector
from app.schemas.io import FacePrediction, JerseyDetection, CompleteAnalysisResponse, TimeOnlyResponse

logger = logging.getLogger(__name__)
mp_face_detection = mp.solutions.face_detection


class AnalysisService:
    """Servicio de análisis con procesamiento paralelo de componentes"""
    
    def __init__(
        self, 
        face_rec: FaceRecognizer,
        jersey_det: JerseyDetector,
        time_det: TimeOCRDetector,
        max_workers: int = 3
    ):
        self.face_rec = face_rec
        self.jersey_det = jersey_det
        self.time_det = time_det
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        logger.info(f"[INFO] AnalysisService inicializado con {max_workers} workers")
    
    def _detect_faces(self, img_rgb: np.ndarray) -> tuple[List[FacePrediction], float]:
        """
        Detecta y reconoce caras en la imagen
        
        Returns:
            (lista de predicciones de caras, tiempo de ejecución)
        """
        start_time = time.perf_counter()
        faces_out: List[FacePrediction] = []
        
        try:
            # 1. Detección con MediaPipe
            with mp_face_detection.FaceDetection(
                model_selection=1, 
                min_detection_confidence=0.5
            ) as fd:
                res = fd.process(img_rgb)
            
            if not (res and res.detections):
                elapsed = time.perf_counter() - start_time
                logger.debug(f"[FACES] No se detectaron caras en {elapsed:.3f}s")
                return [], elapsed
            
            # 2. Extraer bounding boxes en formato [x, y, w, h]
            h, w = img_rgb.shape[:2]
            bboxes_xywh = []
            det_scores = []
            
            for det in res.detections:
                rb = det.location_data.relative_bounding_box
                x = int(rb.xmin * w)
                y = int(rb.ymin * h)
                width = int(rb.width * w)
                height = int(rb.height * h)
                
                # Validar bbox
                x = max(0, x)
                y = max(0, y)
                width = min(width, w - x)
                height = min(height, h - y)
                
                if width > 0 and height > 0:
                    bboxes_xywh.append([x, y, width, height])
                    det_scores.append(float(det.score[0]) if det.score else 0.0)
            
            if not bboxes_xywh:
                elapsed = time.perf_counter() - start_time
                logger.debug(f"[FACES] Bboxes inválidos en {elapsed:.3f}s")
                return [], elapsed
            
            # 3. Embeddings + clasificación
            predictions = self.face_rec.predict(img_rgb, bboxes_xywh, margin_ratio=0.25)
            
            # 4. Construir respuesta
            for i, (bbox, (label, score)) in enumerate(zip(bboxes_xywh, predictions)):
                x, y, w, h = bbox
                # Convertir a formato [top, right, bottom, left] para compatibilidad
                top = y
                right = x + w
                bottom = y + h
                left = x
                
                faces_out.append(
                    FacePrediction(
                        bbox=[top, right, bottom, left],
                        label=str(label),
                        score=float(score)
                    )
                )
            
            elapsed = time.perf_counter() - start_time
            logger.debug(f"[FACES] Detectadas {len(faces_out)} caras en {elapsed:.3f}s")
            return faces_out, elapsed
            
        except Exception as e:
            elapsed = time.perf_counter() - start_time
            logger.error(f"[ERROR] Error en detección de caras: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return [], elapsed
    
    def _detect_jerseys(self, img_rgb: np.ndarray) -> tuple[List[JerseyDetection], int, float]:
        """
        Detecta camisetas en la imagen
        
        Returns:
            (lista de detecciones, contador Colombia, tiempo de ejecución)
        """
        start_time = time.perf_counter()
        
        try:
            jerseys_raw = self.jersey_det.detect(img_rgb)
            jerseys = [
                JerseyDetection(**j) if isinstance(j, dict) else j 
                for j in jerseys_raw
            ]
            
            colombia_count = sum(1 for j in jerseys if j.team == "Colombia")
            
            elapsed = time.perf_counter() - start_time
            logger.debug(f"[JERSEYS] Detectadas {len(jerseys)} camisetas "
                        f"(COL: {colombia_count}) en {elapsed:.3f}s")
            
            return jerseys, colombia_count, elapsed
            
        except Exception as e:
            elapsed = time.perf_counter() - start_time
            logger.error(f"[ERROR] Error en detección de camisetas: {e}")
            return [], 0, elapsed
    
    def _detect_time(self, img_rgb: np.ndarray) -> tuple[Optional[str], float]:
        """
        Detecta el tiempo del partido usando OCR
        
        Returns:
            (tiempo detectado o None, tiempo de ejecución)
        """
        start_time = time.perf_counter()
        
        try:
            match_time = self.time_det.detect_time(img_rgb)
            elapsed = time.perf_counter() - start_time
            
            if match_time:
                logger.debug(f"[TIME OCR] Detectado tiempo: {match_time} en {elapsed:.3f}s")
            else:
                logger.debug(f"[TIME OCR] No se detectó tiempo en {elapsed:.3f}s")
            
            return match_time, elapsed
            
        except Exception as e:
            elapsed = time.perf_counter() - start_time
            logger.error(f"[ERROR] Error en detección de tiempo: {e}")
            return None, elapsed
    
    def analyze_complete(self, img_pil) -> CompleteAnalysisResponse:
        """
        Análisis completo con procesamiento paralelo: caras + camisetas + tiempo
        
        Args:
            img_pil: Imagen PIL
        
        Returns:
            Respuesta completa con todos los análisis y tiempos de ejecución
        """
        from app.utils.images import pil_to_rgb_numpy
        
        total_start = time.perf_counter()
        img_rgb = pil_to_rgb_numpy(img_pil)
        
        # Ejecutar las 3 tareas en paralelo
        future_faces = self.executor.submit(self._detect_faces, img_rgb)
        future_jerseys = self.executor.submit(self._detect_jerseys, img_rgb)
        future_time = self.executor.submit(self._detect_time, img_rgb)
        
        # Recoger resultados
        faces, face_time = future_faces.result()
        jerseys, col_count, jersey_time = future_jerseys.result()
        match_time, time_ocr_time = future_time.result()
        
        total_elapsed = time.perf_counter() - total_start
        
        logger.info(f"[ANÁLISIS COMPLETO] Finalizado en {total_elapsed:.3f}s "
                   f"(Caras: {face_time:.3f}s, Camisetas: {jersey_time:.3f}s, "
                   f"Tiempo: {time_ocr_time:.3f}s)")
        
        return CompleteAnalysisResponse(
            num_faces=len(faces),
            faces=faces,
            jerseys=jerseys,
            colombia_count=col_count,
            match_time=match_time,
            image_processed=True,
            total_detections=len(faces) + len(jerseys),
            processing_times={
                "total": round(total_elapsed, 3),
                "faces": round(face_time, 3),
                "jerseys": round(jersey_time, 3),
                "time_ocr": round(time_ocr_time, 3)
            }
        )
    
    def analyze_time_only(self, img_pil) -> TimeOnlyResponse:
        """
        Análisis solo del tiempo del partido usando OCR
        
        Args:
            img_pil: Imagen PIL
        
        Returns:
            Respuesta con el tiempo detectado
        """
        from app.utils.images import pil_to_rgb_numpy
        
        total_start = time.perf_counter()
        img_rgb = pil_to_rgb_numpy(img_pil)
        
        match_time, ocr_time = self._detect_time(img_rgb)
        total_elapsed = time.perf_counter() - total_start
        
        logger.info(f"[ANÁLISIS TIEMPO] Finalizado en {total_elapsed:.3f}s")
        
        return TimeOnlyResponse(
            match_time=match_time,
            detected=match_time is not None,
            processing_time=round(total_elapsed, 3)
        )
    
    def __del__(self):
        """Limpieza del executor al destruir el servicio"""
        try:
            self.executor.shutdown(wait=True, cancel_futures=True)
            logger.info("[INFO] AnalysisService executor cerrado")
        except Exception as e:
            logger.error(f"[ERROR] Error cerrando executor: {e}")