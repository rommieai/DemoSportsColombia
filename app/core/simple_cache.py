import time
from typing import Any, Dict, Optional

class SimpleCache:
    """Cache básico con TTL configurable."""

    def __init__(self, ttl_seconds: int = 3600):
        self.store: Dict[str, tuple[float, Any]] = {}
        self.ttl = ttl_seconds

    def get(self, key: str) -> Optional[Any]:
        if key not in self.store:
            return None
        
        ts, value = self.store[key]
        if time.time() - ts > self.ttl:
            del self.store[key]
            return None
        
        return value

    def set(self, key: str, value: Any) -> None:
        self.store[key] = (time.time(), value)

    def clear(self) -> None:
        self.store.clear()
