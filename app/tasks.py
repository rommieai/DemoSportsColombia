import httpx
from app.cache_managerask import football_cache  # CORRECTO
import time
from app.cache_managerask import football_cache  # tu cache de football
from app.core.cache import match_data_cache  # <-- IMPORTAR cache de match_data



async def refresh_match_data(match_id: int):
    """Descarga la información del partido y la guarda en cache."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"http://localhost:8004/football/match-complete/{match_id}")
        if resp.status_code != 200:
            print(f"[WARN] Partido {match_id} no disponible: status {resp.status_code}")
            return None

        data = resp.json()
        if not data:
            print(f"[WARN] Partido {match_id} retornó datos vacíos")
            return None

        # Guardar en ambos caches
        football_cache.set(match_id, data)
        match_data_cache.set(match_id, data)  # <--- Esto es lo que faltaba

        print(f"[CACHE] Partido {match_id} actualizado")
        return data

    except Exception as e:
        print(f"[ERROR] refresh_match_data {match_id}: {e}")
        return None