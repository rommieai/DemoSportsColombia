"""
Reconocedor de caras usando FaceNet (facenet-pytorch) + MLP PyTorch
Compatible con el pipeline de extracción e inferencia actualizado
CON MEDICIONES DE TIEMPO DETALLADAS
"""
import json
import os
import numpy as np
import joblib
import torch
import torch.nn as nn
from torchvision import transforms
from PIL import Image
import cv2
from typing import List, Tuple, Optional
import logging
import time

logger = logging.getLogger(__name__)


# ==========================================================================
# MLP Architecture (igual que en entrenamiento/inferencia)
# ==========================================================================
class MLP(nn.Module):
    """
    MLP personalizado con capas configurables
    Arquitectura idéntica a la usada en entrenamiento
    """
    def __init__(self, in_dim: int, n_classes: int, hidden: List[int], 
                 dropout: float = 0.2, use_bn: bool = True):
        super().__init__()
        layers = []
        last = in_dim
        
        for h in hidden:
            layers.append(nn.Linear(last, h))
            if use_bn:
                layers.append(nn.BatchNorm1d(h))
            layers.append(nn.ReLU())
            if dropout > 0:
                layers.append(nn.Dropout(dropout))
            last = h
        
        layers.append(nn.Linear(last, n_classes))
        self.net = nn.Sequential(*layers)
    
    def forward(self, x):
        return self.net(x)


# ==========================================================================
# FaceNet Recognizer
# ==========================================================================
class FaceRecognizer:
    """
    Reconocedor de caras usando:
    - FaceNet (InceptionResnetV1 pretrained en VGGFace2) para embeddings
    - Scaler + PCA para normalización/reducción dimensional
    - MLP de PyTorch para clasificación
    """
    
    def __init__(self, model_path: str, scaler_path: str, labels_json: str, 
                 pca_path: Optional[str] = None, device: Optional[str] = None):
        """
        Args:
            model_path: Ruta al checkpoint de PyTorch (model.pt)
            scaler_path: Ruta al scaler (scaler.joblib)
            labels_json: Ruta al archivo con labels (label_encoder.json)
            pca_path: Ruta al PCA (pca.joblib), opcional
            device: Device de PyTorch ('cuda' o 'cpu'), auto-detecta si None
        """
        self.loaded = False
        self.device = device or ('cuda' if torch.cuda.is_available() else 'cpu')
        self.device = torch.device(self.device)
        
        # Verificar que los archivos existen
        required_files = [model_path, scaler_path, labels_json]
        if not all(os.path.exists(p) for p in required_files):
            logger.error("Archivos de modelo no encontrados")
            return
        
        try:
            t_start = time.perf_counter()
            
            # 1. Cargar FaceNet (backbone para embeddings)
            logger.info("Cargando FaceNet (InceptionResnetV1)...")
            t1 = time.perf_counter()
            from facenet_pytorch import InceptionResnetV1
            self.facenet = InceptionResnetV1(pretrained='vggface2').eval().to(self.device)
            logger.info(f"[TIMING] FaceNet cargado en {(time.perf_counter()-t1):.3f}s")
            
            # 2. Transform para FaceNet (EXACTO al usado en entrenamiento)
            self.transform = transforms.Compose([
                transforms.Resize((160, 160)),
                transforms.ToTensor(),
                transforms.Normalize([0.5, 0.5, 0.5], [0.5, 0.5, 0.5]),  # [-1, 1]
            ])
            
            # 3. Cargar MLP classifier
            logger.info(f"Cargando MLP desde {model_path}...")
            t2 = time.perf_counter()
            ckpt = torch.load(model_path, map_location=self.device)
            
            # Reconstruir arquitectura del MLP
            in_dim = ckpt["in_dim"]
            n_classes = ckpt["n_classes"]
            hidden = ckpt["hidden"]
            dropout = ckpt.get("dropout", 0.2)
            use_bn = ckpt.get("use_bn", True)
            
            self.mlp = MLP(in_dim, n_classes, hidden, dropout, use_bn).to(self.device)
            self.mlp.load_state_dict(ckpt["state_dict"])
            self.mlp.eval()
            
            logger.info(f"[TIMING] MLP cargado en {(time.perf_counter()-t2):.3f}s")
            logger.info(f"MLP: {in_dim}D → {hidden} → {n_classes} clases")
            
            # 4. Cargar scaler
            logger.info(f"Cargando scaler desde {scaler_path}...")
            t3 = time.perf_counter()
            self.scaler = joblib.load(scaler_path)
            logger.info(f"[TIMING] Scaler cargado en {(time.perf_counter()-t3):.3f}s")
            
            # 5. Cargar PCA (opcional)
            self.pca = None
            if pca_path and os.path.exists(pca_path):
                logger.info(f"Cargando PCA desde {pca_path}...")
                t4 = time.perf_counter()
                self.pca = joblib.load(pca_path)
                logger.info(f"[TIMING] PCA cargado en {(time.perf_counter()-t4):.3f}s")
            
            # 6. Cargar labels
            logger.info(f"Cargando labels desde {labels_json}...")
            with open(labels_json, "r", encoding="utf-8") as f:
                meta = json.load(f)
            self.labels = np.array(meta.get("classes_", meta.get("classes", [])))
            
            total_time = time.perf_counter() - t_start
            logger.info(f"✓ FaceRecognizer cargado completamente en {total_time:.3f}s")
            logger.info(f"  Clases: {list(self.labels)}")
            logger.info(f"  Device: {self.device}")
            
            self.loaded = True
            
        except Exception as e:
            logger.error(f"Error cargando FaceRecognizer: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self.loaded = False
    
    @torch.no_grad()
    def _compute_embedding(self, face_rgb: np.ndarray) -> np.ndarray:
        """
        Calcula embedding de 512-D usando FaceNet
        
        Args:
            face_rgb: Imagen de cara en formato RGB (numpy array)
        
        Returns:
            Embedding de 512 dimensiones
        """
        t_start = time.perf_counter()
        
        # Convertir a PIL y aplicar transform
        pil_img = Image.fromarray(face_rgb)
        tensor = self.transform(pil_img).unsqueeze(0).to(self.device)
        
        t_transform = time.perf_counter()
        
        # Extraer embedding
        embedding = self.facenet(tensor).detach().cpu().numpy()[0]  # (512,)
        
        t_inference = time.perf_counter()
        
        logger.debug(
            f"[TIMING] Embedding computado | "
            f"Transform: {(t_transform - t_start)*1000:.2f}ms | "
            f"Inference: {(t_inference - t_transform)*1000:.2f}ms | "
            f"Total: {(t_inference - t_start)*1000:.2f}ms"
        )
        
        return embedding.astype(np.float32)
    
    def encodings(self, img_rgb: np.ndarray, bboxes_xywh: List[List[int]], 
                  margin_ratio: float = 0.25) -> np.ndarray:
        """
        Extrae embeddings de múltiples caras en una imagen
        
        Args:
            img_rgb: Imagen completa en RGB
            bboxes_xywh: Lista de bounding boxes en formato [x, y, w, h]
            margin_ratio: Margen adicional alrededor de la cara (default: 0.25)
        
        Returns:
            Array de embeddings (N x 512)
        """
        if not self.loaded:
            return np.empty((0, 512), dtype=np.float32)
        
        t_start = time.perf_counter()
        embeddings = []
        H, W = img_rgb.shape[:2]
        
        logger.debug(f"[TIMING] Iniciando extracción de embeddings para {len(bboxes_xywh)} caras")
        
        for i, bbox in enumerate(bboxes_xywh):
            t_face_start = time.perf_counter()
            
            x, y, w, h = bbox
            
            # Aplicar margen
            mx = int(w * margin_ratio)
            my = int(h * margin_ratio)
            
            x0 = max(0, x - mx)
            y0 = max(0, y - my)
            x1 = min(W, x + w + mx)
            y1 = min(H, y + h + my)
            
            if x1 <= x0 or y1 <= y0:
                # Bbox inválido, usar embedding cero
                logger.warning(f"Bbox inválido para cara {i}: {bbox}")
                embeddings.append(np.zeros(512, dtype=np.float32))
                continue
            
            # Recortar cara
            face_crop = img_rgb[y0:y1, x0:x1]
            
            try:
                # Calcular embedding
                emb = self._compute_embedding(face_crop)
                embeddings.append(emb)
                
                t_face_end = time.perf_counter()
                logger.debug(f"[TIMING] Cara {i} procesada en {(t_face_end-t_face_start)*1000:.2f}ms")
                
            except Exception as e:
                logger.warning(f"Error calculando embedding para cara {i}: {e}")
                embeddings.append(np.zeros(512, dtype=np.float32))
        
        result = np.vstack(embeddings) if embeddings else np.empty((0, 512), dtype=np.float32)
        
        t_total = time.perf_counter() - t_start
        logger.info(
            f"[TIMING] Embeddings extraídos | "
            f"Caras: {len(bboxes_xywh)} | "
            f"Tiempo total: {t_total:.3f}s | "
            f"Promedio por cara: {(t_total/len(bboxes_xywh)*1000):.2f}ms"
        )
        
        return result
    
    @torch.no_grad()
    def classify(self, embeddings: np.ndarray) -> List[Tuple[str, float]]:
        """
        Clasifica embeddings usando MLP
        
        Args:
            embeddings: Array de embeddings (N x 512)
        
        Returns:
            Lista de (label, probabilidad) para cada embedding
        """
        if not self.loaded or embeddings.size == 0:
            return []
        
        t_start = time.perf_counter()
        
        try:
            # 1. Normalizar con scaler
            t1 = time.perf_counter()
            X = self.scaler.transform(embeddings)
            t_scaler = time.perf_counter() - t1
            
            # 2. Aplicar PCA si existe
            t2 = time.perf_counter()
            if self.pca is not None:
                X = self.pca.transform(X)
            t_pca = time.perf_counter() - t2
            
            # 3. Clasificar con MLP
            t3 = time.perf_counter()
            X_tensor = torch.from_numpy(X).float().to(self.device)
            logits = self.mlp(X_tensor)
            probs = torch.softmax(logits, dim=1).detach().cpu().numpy()
            t_mlp = time.perf_counter() - t3
            
            # 4. Obtener predicción de cada embedding
            t4 = time.perf_counter()
            results = []
            for prob_vec in probs:
                pred_idx = int(np.argmax(prob_vec))
                label = str(self.labels[pred_idx]) if pred_idx < len(self.labels) else "unknown"
                confidence = float(prob_vec[pred_idx])
                results.append((label, confidence))
            t_postprocess = time.perf_counter() - t4
            
            t_total = time.perf_counter() - t_start
            
            logger.info(
                f"[TIMING] Clasificación completada | "
                f"Faces: {len(embeddings)} | "
                f"Scaler: {t_scaler*1000:.2f}ms | "
                f"PCA: {t_pca*1000:.2f}ms | "
                f"MLP: {t_mlp*1000:.2f}ms | "
                f"Postprocess: {t_postprocess*1000:.2f}ms | "
                f"Total: {t_total*1000:.2f}ms"
            )
            
            return results
            
        except Exception as e:
            logger.error(f"Error en clasificación: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return [("unknown", 0.0)] * len(embeddings)
    
    def predict(self, img_rgb: np.ndarray, bboxes_xywh: List[List[int]], 
                margin_ratio: float = 0.25) -> List[Tuple[str, float]]:
        """
        Pipeline completo: embeddings + clasificación
        
        Args:
            img_rgb: Imagen en RGB
            bboxes_xywh: Lista de bounding boxes [x, y, w, h]
            margin_ratio: Margen alrededor de caras
        
        Returns:
            Lista de (label, confidence)
        """
        t_start = time.perf_counter()
        
        embeddings = self.encodings(img_rgb, bboxes_xywh, margin_ratio)
        results = self.classify(embeddings)
        
        t_total = time.perf_counter() - t_start
        logger.info(f"[TIMING] predict() completado en {t_total:.3f}s")
        
        return results


# ==========================================================================
# Compatibilidad con la API antigua (para migration sin romper código)
# ==========================================================================
class FaceRecognizerCompat(FaceRecognizer):
    """
    Wrapper para mantener compatibilidad con la API anterior
    Convierte formato de bboxes y respuestas
    """
    
    def encodings(self, img_rgb: np.ndarray, bboxes_trbl: List[List[int]], 
                  **kwargs) -> np.ndarray:
        """
        Versión compatible que acepta bboxes en formato [top, right, bottom, left]
        y los convierte a [x, y, w, h]
        """
        # Convertir [top, right, bottom, left] → [x, y, w, h]
        bboxes_xywh = []
        for bbox in bboxes_trbl:
            top, right, bottom, left = bbox
            x = left
            y = top
            w = right - left
            h = bottom - top
            bboxes_xywh.append([x, y, w, h])
        
        # Llamar al método padre con formato correcto
        return super().encodings(img_rgb, bboxes_xywh, margin_ratio=0.25)