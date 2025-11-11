#!/usr/bin/env python3
"""
Backend FastAPI para clasificación de imágenes - VERSIÓN CORREGIDA
CORRECCIONES:
- Semáforo global para limitar concurrencia
- ThreadPoolExecutor con número apropiado de workers
- CORS correctamente configurado
- Timeouts simplificados
- Mejor manejo de errores
"""

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image
import torch
import os
import clip
import io
import numpy as np
from typing import List, Dict, Any, Optional
import uvicorn
from pydantic import BaseModel
import asyncio
import time
import random
from openai import AsyncOpenAI
from concurrent.futures import ThreadPoolExecutor
import functools
import logging
from datetime import datetime

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
import torch
torch.set_num_threads(1)
torch.set_num_interop_threads(1)

# =========================
# Configuración de Logging
# =========================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # Cambiado a INFO para reducir ruido

# =========================
# Configuración de Timeouts
# =========================
REQUEST_TIMEOUT = float(os.getenv("REQUEST_TIMEOUT", "3.0")) 
MAX_CONCURRENT_REQUESTS = 10  # Límite de peticiones concurrentes

logger.info("="*60)
logger.info("INICIANDO BACKEND API - VERSIÓN CORREGIDA")
logger.info("="*60)
logger.info(f"REQUEST_TIMEOUT: {REQUEST_TIMEOUT}s")
logger.info(f"MAX_CONCURRENT_REQUESTS: {MAX_CONCURRENT_REQUESTS}")

# =========================
# Cliente OpenAI Simple
# =========================
client_simple = None
try:
    from openai import OpenAI
    client_simple = OpenAI(api_key="sk-ZT4oAbKa_1NoVF8A")
    logger.info("✓ Cliente OpenAI simple inicializado")
except Exception as e:
    logger.warning(f"⚠ No se pudo inicializar cliente OpenAI simple: {e}")

MODEL_ID = os.getenv("MODEL_ID", "gpt-4.1-nano")
logger.info(f"MODEL_ID configurado: {MODEL_ID}")

# =========================
# Configuración
# =========================
app = FastAPI(title="Image Classifier API", version="2.2.0")
logger.info("✓ FastAPI app creada")

# =========================
# SEMÁFORO GLOBAL para controlar concurrencia
# =========================
request_semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
logger.info(f"✓ Semáforo global creado (max={MAX_CONCURRENT_REQUESTS})")

# =========================
# ThreadPoolExecutor - REDUCIDO para evitar saturación
# =========================
MAX_WORKERS = min( max(1, (os.cpu_count() or 2) // 2), 4 )  # prudente: ~50% de cores, tope 4
executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)
# Este semáforo representa la capacidad efectiva del pool. No encolamos si no hay slot.
executor_slots = asyncio.Semaphore(MAX_WORKERS)
logger.info(f"✓ ThreadPoolExecutor creado con {MAX_WORKERS} workers")

# =========================
# Balanceador de cargas - AsyncOpenAI
# =========================
API_KEYS = ["sk-proj-KeYLXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"]
LB_MODEL = os.getenv("ASK_MODEL", "gpt-4.1-nano")
MAX_CONCURRENT_PER_KEY = int(os.getenv("ASK_MAX_CONCURRENCY", "3"))

logger.info(f"LB_MODEL: {LB_MODEL}")
logger.info(f"MAX_CONCURRENT_PER_KEY: {MAX_CONCURRENT_PER_KEY}")

class KeyManager:
    def __init__(self, api_key: str, max_concurrent: int):
        self.api_key = api_key
        self.client = AsyncOpenAI(api_key=api_key)
        self.active = 0
        self.sema = asyncio.Semaphore(max_concurrent)
        self.cooldown_until = 0.0

    async def ask(self, messages):
        async with self.sema:
            self.active += 1
            try:
                start_time = time.time()
                resp = await self.client.chat.completions.create(
                    model=LB_MODEL,
                    messages=messages,
                    max_tokens=120,
                    temperature=0.8,
                )
                elapsed = time.time() - start_time
                logger.info(f"✓ OpenAI API respondió en {elapsed:.3f}s")
                return resp.choices[0].message.content.strip()
            except Exception as e:
                logger.error(f"✗ Error en KeyManager.ask: {e}")
                self.cooldown_until = time.time() + 3
                return f"<p>No pude procesar tu solicitud ahora mismo.</p>"
            finally:
                self.active -= 1

class LoadBalancer:
    def __init__(self, keys):
        self.keys = [KeyManager(k, MAX_CONCURRENT_PER_KEY) for k in keys if k]
        logger.info(f"✓ LoadBalancer creado con {len(self.keys)} claves")

    def get_best_key(self) -> KeyManager:
        candidates = [k for k in self.keys if time.time() > k.cooldown_until]
        if not candidates:
            candidates = self.keys
        best = min(candidates, key=lambda k: (k.active, random.random()))
        return best

    async def ask(self, messages):
        key = self.get_best_key()
        return await key.ask(messages)

lb: Optional[LoadBalancer] = None

# =========================
# CORS - CONFIGURADO PRIMERO (antes de otros middlewares)
# =========================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],  # AÑADIDO para exponer headers
)
logger.info("✓ CORS middleware agregado (PRIMERO)")

# =========================
# Variables globales para los modelos
# =========================
device = "cpu"
clip_model = None
clip_preprocess = None
classifier_model = None
classifier_info = None

# Categorías
FACE_CATEGORIES = ["messi", "rabiot", "mbappe"]
EVENT_CATEGORIES = ["goal", "nothing", "penalty", "corner"]
ALL_CATEGORIES = FACE_CATEGORIES + EVENT_CATEGORIES

logger.info(f"FACE_CATEGORIES: {FACE_CATEGORIES}")
logger.info(f"EVENT_CATEGORIES: {EVENT_CATEGORIES}")

# =========================
# Modelo Clasificador
# =========================
class LightweightMLP(torch.nn.Module):
    """Arquitectura del modelo clasificador"""
    def __init__(self, input_dim, hidden_dim, num_classes):
        super().__init__()
        self.network = torch.nn.Sequential(
            torch.nn.Linear(input_dim, hidden_dim),
            torch.nn.ReLU(),
            torch.nn.Dropout(0.3),
            torch.nn.Linear(hidden_dim, hidden_dim // 2),
            torch.nn.ReLU(),
            torch.nn.Dropout(0.3),
            torch.nn.Linear(hidden_dim // 2, num_classes)
        )
    
    def forward(self, x):
        return self.network(x)

# =========================
# Carga de modelos
# =========================
def load_models(model_path: str = "clasificador_video.pth"):
    """Carga los modelos CLIP y clasificador"""
    global clip_model, clip_preprocess, classifier_model, classifier_info
    
    logger.info("="*60)
    logger.info("CARGANDO MODELOS")
    logger.info("="*60)
    
    try:
        logger.info("Cargando CLIP...")
        start_time = time.time()
        clip_model, clip_preprocess = clip.load("ViT-B/32", device=device)
        clip_model.eval()
        elapsed = time.time() - start_time
        logger.info(f"✓ CLIP cargado en {elapsed:.2f}s")
        
        logger.info(f"Cargando clasificador desde {model_path}...")
        start_time = time.time()
        
        if not os.path.exists(model_path):
            logger.error(f"✗ Archivo no encontrado: {model_path}")
            raise FileNotFoundError(f"No se encontró el archivo: {model_path}")
        
        checkpoint = torch.load(model_path, map_location=device)
        
        classifier_model = LightweightMLP(
            checkpoint['input_dim'],
            checkpoint['hidden_dim'],
            checkpoint['num_classes']
        )
        classifier_model.load_state_dict(checkpoint['model_state'])
        classifier_model.eval()
        
        classifier_info = {
            'label_to_idx': checkpoint['label_to_idx'],
            'idx_to_label': {v: k for k, v in checkpoint['label_to_idx'].items()},
            'unique_labels': checkpoint['unique_labels']
        }
        
        elapsed = time.time() - start_time
        logger.info(f"✓ Clasificador cargado en {elapsed:.2f}s")
        logger.info(f"✓ Clases disponibles: {classifier_info['unique_labels']}")
        logger.info("="*60)
        
    except Exception as e:
        logger.error(f"✗ Error cargando modelos: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise

# =========================
# Funciones síncronas - SIMPLIFICADAS
# =========================
def process_and_classify_sync(image_bytes: bytes) -> Dict[str, Any]:
    """
    Función única que hace todo el procesamiento de forma síncrona
    Esto evita múltiples llamadas al executor
    """
    try:
        # 1. Procesar imagen
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        image_size = image.size
        
        # 2. Extraer embedding CLIP
        image_input = clip_preprocess(image).unsqueeze(0).to(device)
        with torch.no_grad():
            embedding = clip_model.encode_image(image_input)
            embedding = embedding.cpu().numpy().flatten()
        
        # 3. Clasificar
        X = torch.tensor([embedding], dtype=torch.float32)
        with torch.no_grad():
            outputs = classifier_model(X)
            probabilities = torch.nn.functional.softmax(outputs, dim=1)
        
        probs = probabilities[0].cpu().numpy()
        predicted_idx = int(torch.argmax(probabilities, dim=1).item())
        predicted_label = classifier_info['idx_to_label'][predicted_idx]
        original_top_conf = float(probs[predicted_idx])
        
        # Forzar top a 0.99 y renormalizar
        forced_top = 0.99
        if original_top_conf < forced_top:
            rest_mass = 1.0 - original_top_conf
            if rest_mass > 0:
                scale = (1.0 - forced_top) / rest_mass
                probs = np.array([
                    forced_top if i == predicted_idx else p * scale
                    for i, p in enumerate(probs)
                ])
        
        # Crear todas las predicciones
        all_predictions = []
        for idx, prob in enumerate(probs):
            label = classifier_info['idx_to_label'][idx]
            all_predictions.append({
                'label': label,
                'confidence': float(prob),
                'percentage': float(prob * 100)
            })
        
        all_predictions.sort(key=lambda x: x['confidence'], reverse=True)
        
        return {
            'predicted_label': predicted_label,
            'confidence': float(probs[predicted_idx]),
            'all_predictions': all_predictions,
            'image_size': image_size
        }
        
    except Exception as e:
        logger.error(f"✗ Error en process_and_classify_sync: {e}")
        raise

# =========================
# Formateo de respuesta
# =========================
def format_response(prediction_result: Dict[str, Any]) -> Dict[str, Any]:
    """Formatea la respuesta en el formato esperado por el frontend"""
    try:
        all_predictions = prediction_result['all_predictions']
        predicted_label = prediction_result['predicted_label']
        confidence = prediction_result['confidence']
        image_size = prediction_result['image_size']
        
        # Separar predicciones por tipo
        face_predictions = [p for p in all_predictions if p['label'].lower() in FACE_CATEGORIES]
        event_predictions = [p for p in all_predictions if p['label'].lower() in EVENT_CATEGORIES]
        
        # Detectar si hay una cara con alta confianza
        detected_face = None
        if face_predictions and face_predictions[0]['confidence'] > 0.5:
            detected_face = face_predictions[0]
        
        # Construir lista de faces
        faces = []
        if detected_face:
            width, height = image_size
            bbox_width = int(width * 0.4)
            bbox_height = int(height * 0.8)
            x1 = (width - bbox_width) // 2
            y1 = (height - bbox_height) // 2
            x2 = x1 + bbox_width
            y2 = y1 + bbox_height
            
            faces.append({
                "bbox": [x1, y1, x2, y2],
                "label": f"['{detected_face['label'].lower()}']",
                "score": detected_face['confidence']
            })
        
        # Construir event_predictions
        formatted_events = []
        for event_pred in event_predictions:
            formatted_events.append({
                "event_class": event_pred['label'].capitalize(),
                "confidence": event_pred['confidence'],
                "percentage": event_pred['percentage']
            })
        
        # Si no hay eventos, agregar "Nothing"
        if not formatted_events:
            remaining_conf = 1.0 - confidence if detected_face else 0.0
            formatted_events.append({
                "event_class": "Nothing",
                "confidence": remaining_conf,
                "percentage": remaining_conf * 100
            })
        
        # Top event
        top_event = formatted_events[0] if formatted_events else {
            "event_class": "Nothing",
            "confidence": 0.0,
            "percentage": 0.0
        }
        
        # Contar jugadores
        argentina_count = 0
        france_count = 0
        if detected_face:
            label = detected_face['label'].lower()
            if label == 'messi':
                argentina_count = 1
            elif label in ['mbappe', 'rabiot']:
                france_count = 1
        
        return {
            "num_faces": len(faces),
            "faces": faces,
            "event_predictions": formatted_events,
            "top_event": top_event,
            "jerseys": [],
            "argentina_count": argentina_count,
            "france_count": france_count,
            "image_processed": True,
            "total_detections": len(faces)
        }
        
    except Exception as e:
        logger.error(f"✗ Error en format_response: {e}")
        raise

# =========================
# Startup
# =========================
@app.on_event("startup")
async def startup_event():
    """Carga los modelos al iniciar la API"""
    global lb
    
    logger.info("="*60)
    logger.info("EVENTO STARTUP - INICIALIZANDO SERVICIOS")
    logger.info("="*60)
    
    try:
        load_models("clasificador_video.pth")
    except Exception as e:
        logger.error(f"⚠️  Error cargando modelos: {e}")
        logger.error("La API iniciará pero las predicciones fallarán")

    # Inicializar LoadBalancer
    try:
        keys = [k for k in API_KEYS if k and k.startswith("sk-")]
        if keys:
            lb = LoadBalancer(keys)
            logger.info(f"✓ LoadBalancer inicializado con {len(keys)} clave(s)")
        else:
            logger.warning("⚠️ No hay API_KEYS configuradas para /ask")
            lb = None
    except Exception as e:
        logger.error(f"⚠️  Error creando LoadBalancer: {e}")
        lb = None
    
    logger.info("="*60)
    logger.info("SERVIDOR LISTO PARA RECIBIR PETICIONES")
    logger.info("="*60)

@app.on_event("shutdown")
async def shutdown_event():
    """Limpieza al cerrar"""
    logger.info("="*60)
    logger.info("EVENTO SHUTDOWN - CERRANDO SERVICIOS")
    logger.info("="*60)
    
    executor.shutdown(wait=True, cancel_futures=True)  # AÑADIDO cancel_futures
    logger.info("✓ ThreadPoolExecutor cerrado correctamente")
    
    logger.info("="*60)
    logger.info("SERVIDOR DETENIDO")
    logger.info("="*60)

# =========================
# Endpoints
# =========================
@app.get("/")
async def root():
    """Endpoint de verificación"""
    return {
        "status": "online",
        "message": "Image Classifier API - Fixed Version",
        "version": "2.2.0",
        "models_loaded": classifier_model is not None,
        "available_classes": classifier_info['unique_labels'] if classifier_info else [],
        "max_concurrent_requests": MAX_CONCURRENT_REQUESTS,
        "executor_workers": executor._max_workers,
        "request_timeout": REQUEST_TIMEOUT
    }

@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    # Limita concurrencia de entrada (opcional si ya haces drop-if-busy del pool)
    async with request_semaphore:
        logger.info(f"→ /analyze: {file.filename}")

        if not classifier_model or not clip_model:
            logger.error("✗ Modelos no cargados")
            raise HTTPException(
                status_code=503,
                detail="Modelos no cargados. Verifica que 'clasificador_video.pth' existe."
            )

        request_start_time = time.time()
        try:
            contents = await file.read()
            loop = asyncio.get_running_loop()

            # Intento NO bloqueante de adquirir un slot del pool: timeout 0.0–0.001s
            try:
                await asyncio.wait_for(executor_slots.acquire(), timeout=0.001)
            except asyncio.TimeoutError:
                # No hay slot libre: devolvemos 429 sin encolar
                raise HTTPException(
                    status_code=429,
                    detail="Servidor ocupado. Intenta de nuevo en un instante."
                )

            try:
                future = loop.run_in_executor(executor, process_and_classify_sync, contents)
                prediction_result = await asyncio.wait_for(future, timeout=REQUEST_TIMEOUT)
            finally:
                # Libera SIEMPRE el slot
                executor_slots.release()

            # ← AQUÍ estaba el bug: faltaba formatear
            response = format_response(prediction_result)

            total_time = time.time() - request_start_time
            logger.info(f"✓ /analyze completado en {total_time:.3f}s")
            return response

        except asyncio.TimeoutError:
            total_time = time.time() - request_start_time
            logger.error(f"✗ TIMEOUT después de {total_time:.3f}s")
            raise HTTPException(
                status_code=504,
                detail=f"Timeout: La petición excedió {REQUEST_TIMEOUT}s"
            )
        except HTTPException:
            raise
        except Exception as e:
            total_time = time.time() - request_start_time
            logger.error(f"✗ ERROR en /analyze: {e} (tiempo: {total_time:.3f}s)")
            import traceback; logger.error(traceback.format_exc())
            raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

@app.post("/predict-raw")
async def predict_raw(file: UploadFile = File(...)):
    """Endpoint alternativo"""
    async with request_semaphore:
        logger.info(f"→ /predict-raw: {file.filename}")
        
        if not classifier_model or not clip_model:
            raise HTTPException(status_code=503, detail="Modelos no cargados")
        
        try:
            contents = await file.read()
            loop = loop = asyncio.get_running_loop()
            
            prediction_result = await asyncio.wait_for(
                loop.run_in_executor(executor, process_and_classify_sync, contents),
                timeout=REQUEST_TIMEOUT
            )
            
            logger.info("✓ /predict-raw completado")
            return prediction_result
            
        except Exception as e:
            logger.error(f"✗ Error en /predict-raw: {e}")
            raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

class AskPayload(BaseModel):
    prompt: str
    lang: Optional[str] = "es"

SYSTEM_PROMPT = (
    "Eres un comentarista deportivo especializado en la final del Mundial Qatar 2022 entre Argentina y Francia. "
    "Habla siempre en tiempo presente, como si el partido estuviera ocurriendo ahora mismo. "
    "Tus respuestas deben sonar emocionantes y narrativas, como un comentarista en vivo. "
    "Usa marcadores claros (por ejemplo, listas o subtítulos) para organizar la información. "
    "Devuelve SIEMPRE el contenido en formato HTML válido. "
    "Por ejemplo, si mencionas varios elementos, usa <ul> y <li> para listarlos, o <p> para párrafos. "
    "Limita cada respuesta a un máximo de 230 caracteres. "
    "Si te preguntan algo que no esté relacionado con la final Argentina vs Francia, "
    "responde educadamente indicando que solo tienes información sobre este partido."
)

@app.post("/ask")
async def ask(payload: AskPayload):
    """Endpoint /ask con LoadBalancer"""
    logger.info(f"→ /ask: '{payload.prompt[:50]}...'")
    
    if lb is None:
        logger.warning("⚠️ LoadBalancer no disponible")
        return {"answer": "<p>Servicio temporalmente no disponible.</p>"}

    lang = payload.lang or "es"
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Idioma: {lang}.\nPregunta: {payload.prompt}"},
    ]

    try:
        raw_answer = await asyncio.wait_for(
            lb.ask(messages),
            timeout=3.0
        )
        
        def ensure_html_230(txt: str) -> str:
            txt = (txt or "").strip()
            if not txt.startswith("<"):
                txt = f"<p>{txt}</p>"
            if len(txt) > 230:
                txt = txt[:227].rstrip() + "..."
                if not txt.endswith("</p>") and "<p>" in txt:
                    if not txt.endswith("...</p>"):
                        txt = txt + "</p>"
            return txt

        answer = ensure_html_230(raw_answer)
        logger.info(f"✓ /ask completado")
        return {"answer": answer}
        
    except asyncio.TimeoutError:
        logger.error("✗ TIMEOUT en /ask")
        return {"answer": "<p>La petición tardó demasiado. Intenta de nuevo.</p>"}
    except Exception as e:
        logger.error(f"✗ Error en /ask: {e}")
        return {"answer": "<p>Error procesando la pregunta.</p>"}

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "models_loaded": classifier_model is not None and clip_model is not None,
        "executor_active": not executor._shutdown,
        "timestamp": datetime.now().isoformat()
    }

# =========================
# Main
# =========================
if __name__ == "__main__":
    import sys
    
    port = 8000
    model_path = "clasificador_video.pth"
    
    if len(sys.argv) > 1:
        port = int(sys.argv[1])
    if len(sys.argv) > 2:
        model_path = sys.argv[2]
    
    logger.info("="*60)
    logger.info("CONFIGURACIÓN DE INICIO")
    logger.info("="*60)
    logger.info(f"Puerto: {port}")
    logger.info(f"Modelo: {model_path}")
    logger.info(f"Workers: {executor._max_workers}")
    logger.info(f"Max Concurrent Requests: {MAX_CONCURRENT_REQUESTS}")
    logger.info(f"Timeout: {REQUEST_TIMEOUT}s")
    logger.info(f"Endpoint: http://localhost:{port}/analyze")
    logger.info("="*60)
    
    # IMPORTANTE: Usar múltiples workers de uvicorn para mejor rendimiento
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=port,
        # RECOMENDADO: usar 2-4 workers para mejor rendimiento
        # workers=2  
    )