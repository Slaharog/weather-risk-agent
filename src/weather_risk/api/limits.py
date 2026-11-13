"""Protects the OpenAI budget once the app is public (security audit finding, CWE-770).

A per-client sliding window (messages per minute) plus a global daily cap. In memory, so it
resets on restart and is per server instance; enough for a single-instance demo. The OpenAI
project should also have a hard spend limit set in the OpenAI dashboard.
"""

import threading
import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, per_minute: int, per_day: int):
        self.per_minute = per_minute
        self.per_day = per_day
        self._recent: dict[str, deque[float]] = defaultdict(deque)
        self._day = -1
        self._day_count = 0
        self._lock = threading.Lock()

    def allow(self, client: str, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        with self._lock:
            day = int(now // 86_400)
            if day != self._day:
                self._day, self._day_count = day, 0
            if self._day_count >= self.per_day:
                return False
            recent = self._recent[client]
            while recent and recent[0] <= now - 60:
                recent.popleft()
            if len(recent) >= self.per_minute:
                return False
            recent.append(now)
            self._day_count += 1
            return True
