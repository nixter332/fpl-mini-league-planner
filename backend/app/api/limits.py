"""Simple in-memory rate limits (one server process; they reset on restart, which is fine).

They protect two things on a public link: the Claude credit (reasons) and the small free
server (plans take a few seconds of CPU each). The prepaid Claude balance is the hard cap.
"""

import threading
import time
from collections import deque
from collections.abc import Callable

from fastapi import Request


class RateLimiter:
    """At most `limit` events per `window` seconds per key (sliding window)."""

    def __init__(self, limit: int, window: float, clock: Callable[[], float] = time.monotonic) -> None:
        self.limit = limit
        self.window = window
        self.clock = clock
        self._events: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = self.clock()
        with self._lock:
            events = self._events.setdefault(key, deque())
            while events and now - events[0] >= self.window:
                events.popleft()
            if len(events) >= self.limit:
                return False
            events.append(now)
            if len(self._events) > 10_000:  # forget idle keys so memory stays small
                self._events = {k: v for k, v in self._events.items() if v and now - v[-1] < self.window}
            return True


def client_key(request: Request) -> str:
    """The visitor's IP. Behind Vercel and Render the first X-Forwarded-For entry is the client."""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
