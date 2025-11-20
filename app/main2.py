from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import get_settings
from app.api.routers import analyze, health, ask, validate, football, products, players  

# Importar configuración de logging
from app.core.logging_config import setup_logging
from app.middleware import RequestLoggingMiddleware, PerformanceMonitoringMiddleware
import logging

# Configurar logging al inicio
setup_logging(level=logging.INFO)  # Cambiar a DEBUG para más detalles
logger = logging.getLogger(__name__)

def create_app() -> FastAPI:
    logger.info("Iniciando creación de aplicación FastAPI...")
    
    s = get_settings()
    app = FastAPI(
        title="Complete Soccer Analysis API", 
        version="2.0.0",
        description="API para análisis de partidos de fútbol con ML"
    )
    
    # ============== MIDDLEWARES ==============
    
    # 1. Middleware de logging de requests
    app.add_middleware(RequestLoggingMiddleware)
    logger.info("✓ Request logging middleware activado")
    
    # 2. Middleware de monitoreo de rendimiento (alerta si request > 5s)
    app.add_middleware(PerformanceMonitoringMiddleware, slow_request_threshold=5.0)
    logger.info("✓ Performance monitoring middleware activado (umbral: 5.0s)")
    
    # 3. CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["GET","POST","PUT","DELETE","OPTIONS"],
        allow_headers=["*"],
    )
    logger.info(f"✓ CORS configurado para orígenes: {s.CORS_ORIGINS}")
    
    # ============== ROUTERS ==============
    
    app.include_router(analyze.router)
    app.include_router(health.router)
    app.include_router(ask.router)
    #app.include_router(validate.router)
    app.include_router(football.router)
    app.include_router(products.router)
    app.include_router(players.router)
    logger.info("✓ Todos los routers incluidos")
    
    @app.get("/")
    def root():
        return {
            "message": "Complete Soccer Analysis API",
            "version": "2.0.0",
            "endpoints": [
                "/analyze", 
                "/health", 
                "/ask", 
                "/validate", 
                "/football", 
                "/products",
                "/players",
                "/docs"
            ],
        }
    
    @app.on_event("startup")
    async def startup_event():
        logger.info("=" * 80)
        logger.info("INICIANDO COMPLETE SOCCER ANALYSIS API v2.0")
        logger.info("=" * 80)
        
        logger.info("Pre-cargando modelos de ML...")
        
        try:
            from app.api.deps import analysis_service
            import time
            
            t_start = time.perf_counter()
            service = analysis_service()
            t_load = time.perf_counter() - t_start
            
            logger.info(f"[TIMING] Modelos ML cargados en {t_load:.3f}s")
            logger.info(f"  ✓ Reconocimiento facial: {service.face_rec.loaded}")
            logger.info(f"  ✓ Jersey Detector (YOLO): {service.jersey_det.yolo is not None}")
            logger.info(f"  ✓ Time OCR: {service.time_det.reader is not None}")
            
        except Exception as e:
            logger.error(f"❌ Error cargando modelos ML: {str(e)}", exc_info=True)
            logger.warning("⚠️  Los modelos ML pueden no estar disponibles")
        
        logger.info("✓ API de fútbol en vivo disponible en /football")
        logger.info("✓ API de productos de jugadores disponible en /products")
        logger.info("✓ API de estadísticas de jugadores disponible en /players")
        logger.info("=" * 80)
        logger.info("🚀 SISTEMA LISTO - Esperando requests...")
        logger.info("=" * 80)
    
    @app.on_event("shutdown")
    async def shutdown_event():
        logger.info("=" * 80)
        logger.info("🛑 Apagando Complete Soccer Analysis API...")
        logger.info("=" * 80)
    
    return app

app = create_app()

if __name__ == "__main__":
    import uvicorn
    logger.info("Iniciando servidor Uvicorn...")
    uvicorn.run(
        "app.main:app", 
        host="0.0.0.0", 
        port=8003, 
        reload=True,
        log_config=None  # Usar nuestro propio sistema de logging
    )