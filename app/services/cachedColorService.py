"""Servicio de colores con cache en Firebase para mejor performance"""
from app.services.firebase_service import firebase_service
from app.services.color_extraction_service import ColorExtractionService
from typing import Dict

class CachedColorService:
    """Servicio que cachea colores extraídos en Firebase"""
    
    COLLECTION = "team_colors"
    TTL = 2592000  # 30 días (los colores no cambian)
    
    def __init__(self):
        self.extractor = ColorExtractionService()
        self.fb = firebase_service
    
    def get_team_colors(self, team_id: int, logo_url: str) -> Dict[str, str]:
        """
        Obtiene colores de un equipo (con cache)
        
        Args:
            team_id: ID del equipo
            logo_url: URL del logo
        
        Returns:
            {"primary": "#HEX", "secondary": "#HEX"}
        """
        doc_id = f"team_{team_id}"
        
        # 1. Intentar obtener de Firebase
        cached = self.fb.get_if_valid(self.COLLECTION, doc_id)
        if cached:
            print(f"✓ Colores del equipo {team_id} obtenidos de cache")
            return cached
        
        # 2. Extraer colores del logo
        print(f"🎨 Extrayendo colores del equipo {team_id}")
        colors = self.extractor.get_team_colors(logo_url)
        
        # 3. Guardar en Firebase (30 días)
        self.fb.set_with_ttl(self.COLLECTION, doc_id, colors, self.TTL)
        
        return colors


# Función helper actualizada
def get_team_colors_cached(team_id: int, logo_url: str) -> Dict[str, str]:
    """Helper function con cache"""
    service = CachedColorService()
    return service.get_team_colors(team_id, logo_url)