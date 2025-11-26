import asyncio
import time
from typing import Dict


class RateLimiter:
    """Простое ограничение количества запросов для пользователя."""

    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._storage: Dict[int, list[float]] = {}
        self._lock = asyncio.Lock()

    async def check(self, user_id: int) -> int:
        """Возвращает количество секунд ожидания, если лимит превышен."""
        now = time.time()
        async with self._lock:
            timestamps = self._storage.setdefault(user_id, [])
            timestamps = [ts for ts in timestamps if now - ts < self.window_seconds]
            self._storage[user_id] = timestamps
            if len(timestamps) >= self.limit:
                oldest = min(timestamps)
                wait_for = max(1, int(self.window_seconds - (now - oldest)))
                return wait_for
            timestamps.append(now)
            self._storage[user_id] = timestamps
            return 0


def create_default_limiter() -> RateLimiter:
    return RateLimiter(limit=5, window_seconds=60)
