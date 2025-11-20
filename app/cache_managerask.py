
import time
class FootballCache:
    def __init__(self):
        self.data = {}  # {match_id: {"timestamp": ..., "payload": ...}}
        self.ttl_seconds = 120  # auto-expira a los 2 minutos

    def set(self, match_id: int, payload: dict):
        self.data[match_id] = {
            "timestamp": time.time(),
            "payload": payload
        }

    def get(self, match_id: int):
        entry = self.data.get(match_id)
        if not entry:
            return None
        # Auto-expira
        if time.time() - entry["timestamp"] > self.ttl_seconds:
            del self.data[match_id]
            return None
        return entry["payload"]


football_cache = FootballCache()