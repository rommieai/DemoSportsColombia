"""Detector de tiempo del partido usando EasyOCR"""
import cv2
import easyocr
import re
import numpy as np
from typing import Optional, Tuple
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class TimeOCRDetector:
    """Detecta el tiempo del partido (MM:SS) en imágenes usando EasyOCR"""
    
    def __init__(self, gpu: bool = False):
        """
        Inicializa el detector de OCR
        
        Args:
            gpu: Si usar GPU para procesamiento (default: False)
        """
        logger.info("[INFO] Creando reader de EasyOCR...")
        try:
            self.reader = easyocr.Reader(['en'], gpu=gpu)
            logger.info("[INFO] Reader de EasyOCR creado exitosamente.")
        except Exception as e:
            logger.error(f"[ERROR] No se pudo crear reader de EasyOCR: {e}")
            raise
    
    def _clean_text(self, text: str) -> str:
        """
        Limpia el texto que viene de OCR:
        - quita espacios al inicio/fin
        - reemplaza caracteres típicamente mal reconocidos
        - deja solo dígitos y ':'
        """
        t = text.strip()
        
        # Reemplazos típicos (ajusta si ves otros errores)
        t = t.replace(';', ':').replace('.', ':').replace(',', ':')
        t = t.replace('â€˜', ':').replace('â€™', ':').replace('â€œ', ':').replace('â€', ':')
        
        # Dejar solo dígitos y ':'
        t = re.sub(r"[^0-9:]", "", t)
        
        return t
    
    def detect_time(self, image: np.ndarray) -> Optional[str]:
        """
        Detecta el tiempo del partido en formato MM:SS
        
        Args:
            image: Imagen en formato numpy array (RGB)
        
        Returns:
            String con formato "M:SS" o "MM:SS", o None si no se detecta
        """
        try:
            h, w = image.shape[:2] if len(image.shape) >= 2 else (0, 0)
            
            if h == 0 or w == 0:
                logger.warning("[WARN] Imagen inválida (dimensiones 0)")
                return None
            
            logger.debug(f"[DEBUG] Tamaño imagen: {w}x{h}")
            
            # Opcional: redimensionar si la imagen es muy pequeña
            img_to_process = image.copy()
            if max(w, h) < 600:
                scale = 2
                img_to_process = cv2.resize(
                    img_to_process, 
                    None, 
                    fx=scale, 
                    fy=scale, 
                    interpolation=cv2.INTER_LINEAR
                )
                logger.debug(f"[DEBUG] Imagen redimensionada a: {img_to_process.shape[1]}x{img_to_process.shape[0]}")
            
            logger.debug("[INFO] Lanzando EasyOCR...")
            results = self.reader.readtext(img_to_process, detail=1)
            logger.debug(f"[DEBUG] EasyOCR devolvió {len(results)} resultados.")
            
            if not results:
                logger.warning("[WARN] EasyOCR no encontró ningún texto en la imagen.")
                return None
            
            candidate = None
            best_conf = -1.0
            
            # Recorremos todos los textos detectados
            for idx, (bbox, raw_text, conf) in enumerate(results):
                logger.debug(f"\n[DEBUG] Resultado #{idx}")
                logger.debug(f"        bbox: {bbox}")
                logger.debug(f"        raw_text: '{raw_text}'")
                logger.debug(f"        conf: {conf}")
                
                clean = self._clean_text(raw_text)
                logger.debug(f"        limpio: '{clean}'")
                
                if not clean:
                    logger.debug("        [SKIP] Texto vacío después de limpieza.")
                    continue
                
                # Buscamos patrones tipo 9:07, 12:34, 90:00, etc.
                m = re.search(r"(\d{1,2}:\d{2})", clean)
                
                if m:
                    # Caso normal: ya viene con dos puntos
                    time_str = m.group(1)
                    logger.debug(f"        [CANDIDATO] time_str detectado (con ':'): {time_str}")
                else:
                    # Caso alterno: buscar 3-4 dígitos seguidos (934, 1234, etc.)
                    n = re.search(r"(\d{3,4})", clean)
                    if not n:
                        logger.debug("        [SKIP] No encontré patrón tipo M:SS/MM:SS ni secuencia de 3-4 dígitos.")
                        continue
                    
                    digits = n.group(1)
                    logger.debug(f"        [DEBUG] Secuencia numérica sin ':' detectada: {digits}")
                    
                    if len(digits) == 3:
                        # ej: 934 -> 9:34
                        minutes = digits[0]
                        seconds = digits[1:]
                    else:  # len == 4
                        # ej: 1234 -> 12:34
                        minutes = digits[:2]
                        seconds = digits[2:]
                    
                    time_str = f"{int(minutes)}:{seconds}"
                    logger.debug(f"        [CANDIDATO] time_str reconstruido (sin ':'): {time_str}")
                
                # Validación básica
                try:
                    minutes, seconds = time_str.split(":")
                    m_val = int(minutes)
                    s_val = int(seconds)
                    
                    if not (0 <= s_val < 60):
                        logger.debug(f"        [SKIP] Segundos fuera de rango: {s_val}")
                        continue
                    if not (0 <= m_val <= 130):
                        logger.debug(f"        [SKIP] Minutos fuera de rango: {m_val}")
                        continue
                except ValueError:
                    logger.debug("        [SKIP] Error convirtiendo a enteros.")
                    continue
                
                # Seleccionar candidato con mejor confianza
                if conf > best_conf:
                    candidate = time_str
                    best_conf = conf
                    logger.debug(f"        [OK] Nuevo mejor candidato con conf={conf}")
            
            if candidate is None:
                logger.info("[INFO] No se encontró ningún texto que parezca un reloj MM:SS.")
                return None
            
            logger.info(f"[INFO] Mejor tiempo encontrado: {candidate} (conf={best_conf})")
            return candidate
            
        except Exception as e:
            logger.error(f"[ERROR] Error en detect_time: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
