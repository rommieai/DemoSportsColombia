"""Tareas de background para mantener Firebase actualizado"""
from datetime import datetime
from typing import Optional, Dict, Any

from app.services.football_firebase_service import FootballFirebaseService
from app.services.firebase_service import firebase_service
from app.core.config import get_settings
from datetime import datetime, timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
scheduler = AsyncIOScheduler()

settings = get_settings()
football_service = FootballFirebaseService(
    api_key=getattr(settings, 'FOOTBALL_API_KEY', "0e88fe12ff5324e08d0dd7b35659829e")
)

# ===== COLECCIÓN ESPECIAL PARA CACHE DE MATCH DATA =====
MATCH_DATA_COLLECTION = "match_data_cache"
BATCH_STATS_COLLECTION = "team_statistics_batch"

async def refresh_match_data(match_id: int, force: bool = False) -> dict:
    """
    Refresca los datos completos de un partido en Firebase
    
    Esta función se llama desde los endpoints que necesitan datos actualizados.
    Centraliza toda la lógica de actualización.
    
    Args:
        match_id: ID del partido
        force: Si True, fuerza actualización desde API externa
    
    Returns:
        Datos completos del partido
    """
    doc_id = f"match_{match_id}"
    
    # 1. Intentar obtener de Firebase primero (si no es forzado)
    if not force:
        cached = firebase_service.get_if_valid(MATCH_DATA_COLLECTION, doc_id)
        if cached:
            print(f"✓ Match {match_id} data obtenido de Firebase")
            return cached
    
    print(f"🔄 Actualizando match {match_id} desde API externa...")
    
    # 2. Obtener datos frescos de la API
    try:
        # Fixture base
        fixture_data = football_service.get_fixture_by_id(match_id, force_refresh=True)
        
        if fixture_data.get("results", 0) == 0:
            return None
        
        match = fixture_data["response"][0]
        fixture = match["fixture"]
        status = fixture["status"]["short"]
        
        # 3. Obtener eventos
        events = football_service.get_fixture_events(match_id, force_refresh=True)
        
        # 4. Obtener estadísticas (solo si el partido está en vivo o terminado)
        statistics = []
        if status in ["1H", "2H", "HT", "ET", "P", "FT", "AET", "PEN", "LIVE"]:
            statistics = football_service.get_fixture_statistics(match_id, force_refresh=True)
        
        # 5. Construir objeto completo
        complete_data = {
            "fixture": match,
            "events": events,
            "statistics": statistics,
            "last_updated": datetime.now(timezone.utc).isoformat()
        }
        
        # 6. Determinar TTL basado en estado
        ttl = _get_ttl_for_match_state(status)
        
        # 7. Guardar en Firebase
        firebase_service.set_with_ttl(
            MATCH_DATA_COLLECTION, 
            doc_id, 
            complete_data, 
            ttl
        )
        
        print(f"✅ Match {match_id} actualizado en Firebase (TTL: {ttl}s)")
        
        return complete_data
    
    except Exception as e:
        print(f"❌ Error actualizando match {match_id}: {str(e)}")
        return None


def _get_ttl_for_match_state(status: str) -> int:
    """
    Determina el TTL apropiado según el estado del partido
    
    Estrategia inteligente:
    - Partido en vivo: 60 segundos (datos cambian rápido)
    - Partido finalizado: 3600 segundos (1 hora - datos estáticos)
    - Partido futuro: 300 segundos (5 minutos)
    - Partido suspendido/pospuesto: 600 segundos (10 minutos)
    """
    # Partido en vivo - actualización frecuente
    if status in ["1H", "2H", "HT", "ET", "P", "BT", "LIVE"]:
        return 60
    
    # Partido finalizado - datos estáticos
    if status in ["FT", "AET", "PEN"]:
        return 3600
    
    # Partido suspendido/cancelado - actualización moderada
    if status in ["SUSP", "INT", "PST", "CANC", "ABD"]:
        return 600
    
    # Partido futuro - actualización regular
    if status in ["TBD", "NS"]:
        return 300
    
    # Default
    return 300


async def refresh_live_matches() -> dict:
    """
    Refresca la lista de partidos en vivo
    
    Esta función debe ejecutarse periódicamente (cada 60 segundos)
    para mantener actualizada la lista de partidos en vivo.
    """
    try:
        data = football_service.get_live_fixtures(force_refresh=True)
        print(f"✅ Live matches actualizados: {data.get('results', 0)} partidos")
        return data
    except Exception as e:
        print(f"❌ Error actualizando live matches: {str(e)}")
        return {"results": 0, "response": []}


async def cleanup_expired_documents():
    """
    Limpia documentos expirados de todas las colecciones
    
    Esta función debe ejecutarse periódicamente (ej: cada hora)
    para mantener Firebase limpio y reducir costos de almacenamiento.
    """
    collections = [
        football_service.COLLECTION_LIVE_FIXTURES,
        football_service.COLLECTION_FIXTURES,
        football_service.COLLECTION_LINEUPS,
        football_service.COLLECTION_STATISTICS,
        football_service.COLLECTION_EVENTS,
        football_service.COLLECTION_TEAM_STATS,
        football_service.COLLECTION_TEAM_SEASONS,
        MATCH_DATA_COLLECTION
    ]
    
    total_cleaned = 0
    
    for collection in collections:
        try:
            count = firebase_service.cleanup_expired(collection)
            total_cleaned += count
            if count > 0:
                print(f"🧹 Limpiados {count} documentos de {collection}")
        except Exception as e:
            print(f"❌ Error limpiando {collection}: {str(e)}")
    
    print(f"✅ Limpieza completada: {total_cleaned} documentos eliminados")
    return total_cleaned


# ===== HELPER PARA OBTENER MATCH DATA (usado por otros servicios) =====

def get_match_data_from_firebase(match_id: int) -> Optional[dict]:
    """
    Obtiene datos de un partido desde Firebase (sin actualizar)
    
    Esta función es usada por servicios que necesitan los datos
    pero no quieren forzar una actualización (ej: commentary_service).
    
    Args:
        match_id: ID del partido
    
    Returns:
        Datos del partido o None si no existen
    """
    doc_id = f"match_{match_id}"
    return firebase_service.get_if_valid(MATCH_DATA_COLLECTION, doc_id)


def set_match_data_in_firebase(match_id: int, data: dict, ttl: int = 60):
    """
    Guarda datos de un partido en Firebase
    
    Args:
        match_id: ID del partido
        data: Datos completos del partido
        ttl: Tiempo de vida en segundos
    """
    doc_id = f"match_{match_id}"
    firebase_service.set_with_ttl(MATCH_DATA_COLLECTION, doc_id, data, ttl)


async def get_both_teams_stats_cached(
    home_team_id: int,
    away_team_id: int,
    league_id: int,
    season: int,
    force_refresh: bool = False
) -> Dict[str, Any]:
    """
    Obtiene estadísticas de ambos equipos en una sola operación de cache.
    
    OPTIMIZACIÓN: En lugar de 2 llamadas separadas a Firebase/API,
    guarda y recupera ambas estadísticas juntas.
    
    Args:
        home_team_id: ID del equipo local
        away_team_id: ID del equipo visitante
        league_id: ID de la liga
        season: Temporada
        force_refresh: Forzar actualización
    
    Returns:
        {"home": {...}, "away": {...}}
    """
    # Clave de cache para ambos equipos juntos
    cache_key = f"both_{home_team_id}_{away_team_id}_{league_id}_{season}"
    
    # 1. Intentar obtener del cache batch
    if not force_refresh:
        cached = firebase_service.get_if_valid(BATCH_STATS_COLLECTION, cache_key)
        if cached:
            print(f"✓ Estadísticas batch de ambos equipos obtenidas de Firebase")
            return cached
    
    # 2. Si no hay cache, obtener individualmente (pero usando sus caches propios)
    print(f"🔄 Obteniendo estadísticas de ambos equipos...")
    
    home_stats_raw = football_service.get_team_statistics(
        team_id=home_team_id,
        league_id=league_id,
        season=season,
        force_refresh=False  # Usar cache individual si existe
    )
    
    away_stats_raw = football_service.get_team_statistics(
        team_id=away_team_id,
        league_id=league_id,
        season=season,
        force_refresh=False  # Usar cache individual si existe
    )
    
    # 3. Procesar estadísticas
    def process_team_stats(stats_response):
        """Procesa estadísticas crudas a formato simplificado"""
        if not stats_response or stats_response.get("results", 0) == 0:
            return None
        
        stats = stats_response["response"]
        fixtures = stats.get("fixtures", {})
        goals = stats.get("goals", {})
        
        partidos = fixtures.get("played", {}).get("total", 0)
        ganados = fixtures.get("wins", {}).get("total", 0)
        empatados = fixtures.get("draws", {}).get("total", 0)
        perdidos = fixtures.get("loses", {}).get("total", 0)
        
        goles_favor = goals.get("for", {}).get("total", {}).get("total", 0)
        goles_contra = goals.get("against", {}).get("total", {}).get("total", 0)
        
        return {
            "partidos_jugados": partidos,
            "ganados": ganados,
            "empatados": empatados,
            "perdidos": perdidos,
            "goles_favor": goles_favor,
            "goles_contra": goles_contra,
            "diferencia_goles": goles_favor - goles_contra,
            "forma_reciente": stats.get("form", "N/A")[-5:] if stats.get("form") else "N/A",
            "porterias_cero": stats.get("clean_sheet", {}).get("total", 0),
            "rachas": {
                "victorias_seguidas": stats.get("biggest", {}).get("streak", {}).get("wins", 0),
                "derrotas_seguidas": stats.get("biggest", {}).get("streak", {}).get("loses", 0)
            }
        }
    
    both_stats = {
        "home": process_team_stats(home_stats_raw),
        "away": process_team_stats(away_stats_raw)
    }
    
    # 4. Guardar en cache batch (2 horas - mismo TTL que estadísticas individuales)
    firebase_service.set_with_ttl(
        BATCH_STATS_COLLECTION,
        cache_key,
        both_stats,
        7200  # 2 horas
    )
    
    print(f"✓ Estadísticas de ambos equipos guardadas en cache batch")
    
    return both_stats
