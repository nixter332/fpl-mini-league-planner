"""A small JSON disk cache with per-entry expiry.

Each entry is one file under the cache root holding {"saved_at", "expires_at", "data"}.
`expires_at` is an absolute Unix time, or null for "never expires". The client decides
the expiry (e.g. "the next deadline" for shared per-gameweek data); the cache just obeys it.
"""

import json
import os
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "cache"

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


class DiskCache:
    def __init__(self, root: Path = DEFAULT_CACHE_DIR, clock: Callable[[], float] = time.time) -> None:
        self.root = Path(root)
        self.clock = clock

    def path_for(self, key: str) -> Path:
        return self.root / f"{_UNSAFE.sub('_', key).strip('._')}.json"

    def get(self, key: str) -> Any | None:
        """Return cached data, or None on a miss, an expired entry or a corrupt file."""
        path = self.path_for(key)
        try:
            entry = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        expires_at = entry.get("expires_at")
        if expires_at is not None and self.clock() >= expires_at:
            return None
        return entry.get("data")

    def set(
        self,
        key: str,
        data: Any,
        *,
        ttl: float | None = None,
        expires_at: float | None = None,
    ) -> None:
        """Store data. With both ttl and expires_at, the earlier one wins; with neither, it never expires."""
        now = self.clock()
        candidates = [t for t in (expires_at, None if ttl is None else now + ttl) if t is not None]
        entry = {"saved_at": now, "expires_at": min(candidates) if candidates else None, "data": data}

        self.root.mkdir(parents=True, exist_ok=True)
        path = self.path_for(key)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(entry), encoding="utf-8")
        os.replace(tmp, path)  # atomic, so readers never see a half-written file

    def clear(self) -> None:
        if self.root.exists():
            for path in self.root.glob("*.json"):
                path.unlink()
