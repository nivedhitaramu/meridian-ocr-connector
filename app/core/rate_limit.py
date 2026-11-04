"""A small in-memory sliding-window limiter. One process only, which suits the single-API demo."""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, per_minute: int, clock=time.monotonic) -> None:
        self.per_minute = per_minute
        self._clock = clock
        self._lock = threading.Lock()
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        if self.per_minute <= 0:
            return True
        now = self._clock()
        with self._lock:
            # Forget clients with no recent requests, so the table can't grow without limit.
            for other in [k for k, hits in self._hits.items() if hits[-1] <= now - 60]:
                del self._hits[other]
            hits = self._hits[key]
            while hits and hits[0] <= now - 60:
                hits.popleft()
            if len(hits) >= self.per_minute:
                return False
            hits.append(now)
            return True


class DailyLimit:
    """A total for the whole app per UTC day. It protects the model budget, not fairness between clients."""

    def __init__(self, limit: int, clock=time.time) -> None:
        self.limit = limit
        self._clock = clock
        self._lock = threading.Lock()
        self._day = -1
        self._count = 0

    def allow(self) -> bool:
        if self.limit <= 0:
            return True
        day = int(self._clock() // 86400)
        with self._lock:
            if day != self._day:
                self._day, self._count = day, 0
            if self._count >= self.limit:
                return False
            self._count += 1
            return True
