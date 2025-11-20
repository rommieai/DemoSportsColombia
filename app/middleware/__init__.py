"""
Middleware para logging de requests HTTP
Captura información detallada de cada request y response
"""
import time
import json
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
import logging

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware que logea información detallada de cada request:
    - Método HTTP
    - URL path
    - Parámetros query
    - Headers importantes
    - Tiempo de procesamiento
    - Status code
    - Tamaño de la respuesta
    """
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Timestamp de inicio
        start_time = time.perf_counter()
        
        # Información del request
        request_info = {
            "method": request.method,
            "url": str(request.url),
            "path": request.url.path,
            "query_params": dict(request.query_params),
            "client_host": request.client.host if request.client else None,
            "user_agent": request.headers.get("user-agent", "unknown"),
        }
        
        # Log del request entrante
        logger.info(
            f"[REQUEST] {request.method} {request.url.path} | "
            f"Client: {request_info['client_host']} | "
            f"Query: {request_info['query_params']}"
        )
        
        # Procesar request
        try:
            response = await call_next(request)
            
            # Calcular tiempo de procesamiento
            process_time = time.perf_counter() - start_time
            
            # Información de la respuesta
            response_info = {
                "status_code": response.status_code,
                "process_time": round(process_time, 3),
            }
            
            # Agregar header con tiempo de procesamiento
            response.headers["X-Process-Time"] = str(process_time)
            
            # Log del response
            log_level = logging.INFO if response.status_code < 400 else logging.WARNING
            
            logger.log(
                log_level,
                f"[REQUEST] {request.method} {request.url.path} | "
                f"Status: {response.status_code} | "
                f"Time: {process_time:.3f}s"
            )
            
            # Log detallado en DEBUG
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(
                    f"[REQUEST] Detalle completo:\n"
                    f"  Request: {json.dumps(request_info, indent=2)}\n"
                    f"  Response: {json.dumps(response_info, indent=2)}"
                )
            
            return response
            
        except Exception as e:
            # Log de error
            process_time = time.perf_counter() - start_time
            
            logger.error(
                f"[REQUEST] ERROR en {request.method} {request.url.path} | "
                f"Time: {process_time:.3f}s | "
                f"Error: {str(e)}",
                exc_info=True
            )
            
            raise


class PerformanceMonitoringMiddleware(BaseHTTPMiddleware):
    """
    Middleware para monitorear rendimiento y alertar sobre requests lentos
    """
    
    def __init__(self, app: ASGIApp, slow_request_threshold: float = 5.0):
        super().__init__(app)
        self.slow_request_threshold = slow_request_threshold
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.perf_counter()
        
        response = await call_next(request)
        
        process_time = time.perf_counter() - start_time
        
        # Alerta si la request es lenta
        if process_time > self.slow_request_threshold:
            logger.warning(
                f"[PERFORMANCE] ⚠️  Request lento detectado: "
                f"{request.method} {request.url.path} | "
                f"Tiempo: {process_time:.3f}s (umbral: {self.slow_request_threshold}s)"
            )
        
        return response