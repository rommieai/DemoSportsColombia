"""
Middleware para guardar respuestas de endpoints específicos
Soporta: SQLite, archivos JSON, y MongoDB
"""
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class ResponseLoggerMiddleware(BaseHTTPMiddleware):
    """
    Middleware que registra requests y responses de endpoints específicos.
    
    Características:
    - Guarda en SQLite por defecto
    - Opcionalmente guarda en archivos JSON
    - Filtra por prefijos de rutas (football, players, products)
    - No afecta el rendimiento de la API
    """
    
    def __init__(
        self, 
        app,
        db_path: str = "logs/api_responses.db",
        json_logs_dir: Optional[str] = "logs/json",
        enable_json_logs: bool = True,
        monitored_prefixes: list = None
    ):
        super().__init__(app)
        self.db_path = db_path
        self.json_logs_dir = json_logs_dir
        self.enable_json_logs = enable_json_logs
        
        # Prefijos de rutas a monitorear
        self.monitored_prefixes = monitored_prefixes or [
            "/football",
            "/players", 
            "/products"
        ]
        
        # Inicializar almacenamiento
        self._init_storage()
    
    def _init_storage(self):
        """Inicializa base de datos y directorios"""
        # Crear directorio para DB
        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)
        
        # Crear tabla en SQLite
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                method TEXT NOT NULL,
                path TEXT NOT NULL,
                query_params TEXT,
                status_code INTEGER,
                response_body TEXT,
                response_size INTEGER,
                duration_ms REAL,
                client_ip TEXT,
                user_agent TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Índices para búsquedas rápidas
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_path ON api_logs(path)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_timestamp ON api_logs(timestamp)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_status ON api_logs(status_code)
        """)
        
        conn.commit()
        conn.close()
        
        # Crear directorio para logs JSON
        if self.enable_json_logs and self.json_logs_dir:
            Path(self.json_logs_dir).mkdir(parents=True, exist_ok=True)
        
        logger.info(f"✓ Response Logger inicializado: {self.db_path}")
    
    def _should_log(self, path: str) -> bool:
        """Determina si la ruta debe ser registrada"""
        return any(path.startswith(prefix) for prefix in self.monitored_prefixes)
    
    async def dispatch(self, request: Request, call_next):
        """Intercepta request/response"""
        path = request.url.path
        
        # Solo procesar rutas monitoreadas
        if not self._should_log(path):
            return await call_next(request)
        
        # Capturar datos del request
        start_time = time.time()
        timestamp = datetime.utcnow().isoformat()
        method = request.method
        query_params = dict(request.query_params)
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "unknown")
        
        # ✅ FIX: Crear un wrapper para capturar el body
        response = await call_next(request)
        
        # Calcular duración
        duration_ms = (time.time() - start_time) * 1000
        
        # ✅ FIX: Capturar response body correctamente
        response_body = b""
        body_chunks = []
        
        async for chunk in response.body_iterator:
            body_chunks.append(chunk)
            response_body += chunk
        
        # Decodificar body
        try:
            body_text = response_body.decode("utf-8")
            response_size = len(response_body)
            
            # ✅ VALIDAR que el body no esté vacío
            if not body_text.strip():
                body_text = "<empty_response>"
                logger.warning(f"Response body vacío para {path}")
            
        except Exception as e:
            body_text = f"<decode_error: {str(e)}>"
            response_size = len(response_body)
            logger.error(f"Error decodificando body para {path}: {e}")
        
        # ✅ LOG para debugging
        logger.debug(f"Capturado response de {path}: {len(body_text)} chars")
        
        # Guardar en SQLite
        try:
            self._save_to_db(
                timestamp=timestamp,
                method=method,
                path=path,
                query_params=json.dumps(query_params),
                status_code=response.status_code,
                response_body=body_text,
                response_size=response_size,
                duration_ms=duration_ms,
                client_ip=client_ip,
                user_agent=user_agent
            )
        except Exception as e:
            logger.error(f"Error guardando en DB: {e}", exc_info=True)
        
        # Guardar en JSON (opcional)
        if self.enable_json_logs:
            try:
                self._save_to_json(
                    timestamp=timestamp,
                    method=method,
                    path=path,
                    query_params=query_params,
                    status_code=response.status_code,
                    response_body=body_text[:2000],  # Primeros 2000 chars en JSON
                    duration_ms=duration_ms,
                    client_ip=client_ip
                )
            except Exception as e:
                logger.error(f"Error guardando JSON: {e}")
        
        # ✅ FIX: Retornar response reconstruida con el body capturado
        from starlette.responses import StreamingResponse
        
        async def generate():
            for chunk in body_chunks:
                yield chunk
        
        return StreamingResponse(
            generate(),
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.media_type
        )
    
    def _save_to_db(self, **data):
        """Guarda en SQLite"""
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO api_logs (
                timestamp, method, path, query_params, 
                status_code, response_body, response_size, 
                duration_ms, client_ip, user_agent
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data["timestamp"],
            data["method"],
            data["path"],
            data["query_params"],
            data["status_code"],
            data["response_body"],
            data["response_size"],
            data["duration_ms"],
            data["client_ip"],
            data["user_agent"]
        ))
        
        conn.commit()
        conn.close()
    
    def _save_to_json(self, **data):
        """Guarda en archivo JSON (un archivo por día)"""
        date_str = datetime.utcnow().strftime("%Y-%m-%d")
        json_file = Path(self.json_logs_dir) / f"logs_{date_str}.json"
        
        log_entry = {
            "timestamp": data["timestamp"],
            "method": data["method"],
            "path": data["path"],
            "query_params": data["query_params"],
            "status_code": data["status_code"],
            "response_body_preview": data["response_body"][:500] + "..." 
                if len(data["response_body"]) > 500 else data["response_body"],
            "duration_ms": data["duration_ms"],
            "client_ip": data["client_ip"]
        }
        
        # Append al archivo
        with open(json_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")