import numpy as np
import cv2
import os
from typing import List, Dict
from app.core.config import get_settings
from app.schemas.io import JerseyDetection


class JerseyDetector:
    def __init__(self):
        self.yolo = None
        self.custom_classes = [
            "Colombia jersey", "colombia soccer shirt",
            "yellow jersey", "yellow soccer shirt",
            "yellow sports shirt", "amarillo jersey"
        ]
        
        try:
            from ultralytics import YOLOWorld
            s = get_settings()
            weights_path = s.YOLO_WORLD_S_PATH
            model = YOLOWorld(weights_path)
            self.yolo = model
            self.yolo.set_classes(self.custom_classes)
            print("✓ YOLOWorld cargado correctamente para camisetas de Colombia")
        except Exception as e:
            print(f"⚠ YOLOWorld no disponible: {e}")
            self.yolo = None

    def detect_with_yolo(self, image: np.ndarray) -> List[JerseyDetection]:
        """Detectar camisetas usando YOLOWorld de ultralytics"""
        if self.yolo is None:
            print("YOLOWorld no disponible")
            return []
        
        try:
            print("Ejecutando YOLOWorld...")
            results = self.yolo(image, conf=0.25, verbose=False)
            
            detections = []
            
            for result in results:
                if result.boxes is not None and len(result.boxes) > 0:
                    boxes = result.boxes
                    print(f"YOLOWorld detectó {len(boxes)} objetos")
                    
                    for i, box in enumerate(boxes):
                        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                        confidence = float(box.conf[0].cpu().numpy())
                        class_id = int(box.cls[0].cpu().numpy())
                        
                        print(f"  Objeto {i}: clase_id={class_id}, confianza={confidence:.3f}")
                        
                        if class_id < len(self.custom_classes):
                            class_name = self.custom_classes[class_id].lower()
                            
                            # Todas las detecciones son Colombia (amarillo)
                            if any(term in class_name for term in ["colombia", "yellow", "amarillo"]):
                                team = "Colombia"
                            else:
                                team = "Colombia"  # Por defecto Colombia
                            
                            detections.append(JerseyDetection(
                                team=team,
                                bbox=[int(x1), int(y1), int(x2), int(y2)],
                                confidence=confidence
                            ))
                else:
                    print("YOLOWorld: Sin detecciones")
            
            print(f"YOLOWorld completado: {len(detections)} camisetas detectadas")
            return detections
            
        except Exception as e:
            print(f"Error en YOLOWorld: {e}")
            import traceback
            print(traceback.format_exc())
            return []

    def detect_by_colors(self, image: np.ndarray) -> List[JerseyDetection]:
        """Detectar camisetas amarillas de Colombia por colores característicos"""
        detections = []
        height, width = image.shape[:2]
        
        print("Ejecutando detección por colores (amarillo Colombia)...")
        
        hsv = cv2.cvtColor(image, cv2.COLOR_RGB2HSV)
        
        # COLOMBIA - Rangos para amarillo característico
        # Amarillo brillante (como el de la selección Colombia)
        lower_yellow1 = np.array([20, 100, 100])  # H: 20-30 (amarillo)
        upper_yellow1 = np.array([30, 255, 255])
        
        # Amarillo más claro/dorado
        lower_yellow2 = np.array([25, 50, 150])
        upper_yellow2 = np.array([35, 255, 255])
        
        mask_yellow1 = cv2.inRange(hsv, lower_yellow1, upper_yellow1)
        mask_yellow2 = cv2.inRange(hsv, lower_yellow2, upper_yellow2)
        mask_colombia = cv2.bitwise_or(mask_yellow1, mask_yellow2)
        
        # Mejorar máscara con operaciones morfológicas
        kernel = np.ones((5,5), np.uint8)
        mask_colombia = cv2.morphologyEx(mask_colombia, cv2.MORPH_CLOSE, kernel)
        mask_colombia = cv2.morphologyEx(mask_colombia, cv2.MORPH_OPEN, kernel)
        
        def process_contours(mask, team_name, min_area=800):
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            team_detections = []
            
            for contour in contours:
                area = cv2.contourArea(contour)
                if area > min_area:
                    x, y, w, h = cv2.boundingRect(contour)
                    
                    # Validar aspecto de camiseta (proporción ancho/alto razonable)
                    aspect_ratio = w / h
                    if 0.3 <= aspect_ratio <= 2.5:
                        # Calcular confianza basada en área y posición
                        size_confidence = min(area / 15000.0, 1.0)
                        position_bonus = 1.0 if y < height * 0.7 else 0.8
                        final_confidence = min(size_confidence * position_bonus, 1.0)
                        
                        team_detections.append(JerseyDetection(
                            team=team_name,
                            bbox=[x, y, x + w, y + h],
                            confidence=float(final_confidence)
                        ))
            
            return team_detections
        
        detections.extend(process_contours(mask_colombia, "Colombia"))
        
        print(f"Detección por colores completada: {len(detections)} camisetas de Colombia")
        return detections

    def detect(self, image: np.ndarray) -> List[JerseyDetection]:
        """Método principal: YOLOWorld primero, colores como backup"""
        yolo_detections = self.detect_with_yolo(image) if self.yolo else []
        
        if len(yolo_detections) > 0:
            print(f"✓ Usando YOLOWorld: {len(yolo_detections)} detecciones")
            return yolo_detections
        
        color_detections = self.detect_by_colors(image)
        print(f"✓ Usando detección por colores: {len(color_detections)} detecciones")
        return color_detections