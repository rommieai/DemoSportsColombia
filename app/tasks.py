import httpx
from app.cache_managerask import football_cache  # CORRECTO
import time


async def refresh_match_data(match_id: int):
    """Descarga la información del partido y la guarda en cache."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"http://localhost:8004/football/match-complete/{match_id}")

        resp.raise_for_status()

        data = resp.json()
        football_cache.set(match_id, data)  # Guarda en cache

        print(f"[CACHE] Partido {match_id} actualizado a las {time.time()}")
        return data

    except Exception as e:
        print(f"Error refrescando datos del partido {match_id}: {e}")
        return None
