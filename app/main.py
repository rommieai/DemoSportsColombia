from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import get_settings
from app.api.routers import analyze, health, ask, validate, football, products, players  

def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(title="Complete Soccer Analysis API", version="2.0.0")
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET","POST","PUT","DELETE","OPTIONS"],
        allow_headers=["*"],
    )
    
    app.include_router(analyze.router)
    app.include_router(health.router)
    app.include_router(ask.router)
    app.include_router(validate.router)
    app.include_router(football.router)
    app.include_router(products.router)
    app.include_router(players.router)
    
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
        print("🚀 Iniciando Complete Soccer Analysis API v2.0...")
        print("📦 Pre-cargando modelos...")
        
        try:
            from app.api.deps import analysis_service
            service = analysis_service()
            
            print(f"✅ Modelos cargados:")
            print(f"  - Reconocimiento facial: {service.face_rec.loaded}")
            print(f"  - Jersey Detector (YOLO): {service.jersey_det.yolo is not None}")
        except Exception as e:
            print(f"⚠️  Error cargando modelos ML: {str(e)}")
            print("⚠️  Los modelos ML pueden no estar disponibles")
        
        print("⚽ API de fútbol en vivo disponible en /football")
        print("🛍️  API de productos de jugadores disponible en /products")
        print("📊 API de estadísticas de jugadores disponible en /players")
        print("🎉 Sistema listo!")
    
    return app

app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8003, reload=True)