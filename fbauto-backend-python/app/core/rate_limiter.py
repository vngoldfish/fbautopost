"""
app/core/rate_limiter.py
In-memory sliding window rate limiter with tiered limits and automatic garbage collection.
Zero external library dependencies (pure Python with collections.deque).
"""

import time
import threading
from collections import deque
from typing import Dict, Tuple

class SlidingWindowRateLimiter:
    """
    Tracks request timestamps within a 60-second sliding window per client bucket.
    Guarantees strict sliding-window rate enforcement without minute-boundary spikes.
    """
    def __init__(self, default_window_seconds: float = 60.0):
        self.window_seconds = default_window_seconds
        self._history: Dict[str, deque] = {}
        self._lock = threading.RLock()
        self._last_cleanup = time.time()

    def is_allowed(self, client_key: str, limit: int) -> Tuple[bool, int]:
        """
        Evaluate if client_key is allowed to execute request under limit.
        Returns: (is_allowed: bool, retry_after_sec: int)
        """
        now = time.time()

        with self._lock:
            # Periodic background cleanup every 300 seconds
            if now - self._last_cleanup > 300.0:
                self._evict_stale_keys(now)

            if client_key not in self._history:
                self._history[client_key] = deque()

            bucket = self._history[client_key]
            cutoff = now - self.window_seconds

            # Evict timestamps older than the sliding window
            while bucket and bucket[0] < cutoff:
                bucket.popleft()

            # Check if limit reached
            if len(bucket) >= limit:
                earliest_active_ts = bucket[0]
                retry_after = max(1, int(earliest_active_ts + self.window_seconds - now) + 1)
                return False, retry_after

            # Record this valid request timestamp
            bucket.append(now)
            return True, 0

    def _evict_stale_keys(self, now: float) -> None:
        """Purge client buckets where all timestamps have expired to prevent memory growth."""
        cutoff = now - self.window_seconds
        stale_keys = [key for key, q in self._history.items() if not q or q[-1] < cutoff]
        for key in stale_keys:
            del self._history[key]
        self._last_cleanup = now

# Global singleton rate limiter instance
rate_limiter = SlidingWindowRateLimiter(default_window_seconds=60.0)
