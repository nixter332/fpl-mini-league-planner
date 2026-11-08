"""FPL API client: every public endpoint we use, behind the disk cache.

Rules this module enforces (see CLAUDE.md):
- Public endpoints only, no login.
- A clear User-Agent, timeouts, retries with backoff, and a minimum gap between live requests.
- Read from the cache first. Shared data (bootstrap, fixtures) expires at the next deadline
  or after a few hours, whichever is sooner. Finished gameweeks' live data never expires.
  Manager, league and per-player data expires after a short time.
"""

import logging
import time
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from typing import Any

import httpx

from app.fpl.cache import DiskCache
from app.fpl.gameweeks import next_deadline
from app.fpl.models import Event

log = logging.getLogger(__name__)

BASE_URL = "https://fantasy.premierleague.com/api/"
USER_AGENT = "fpl-mini-league-planner/0.1 (read-only, public endpoints, cached)"

SHARED_TTL = 6 * 60 * 60  # prices and injury news change daily
LIVE_IN_PROGRESS_TTL = 10 * 60
SHORT_TTL = 15 * 60  # manager, league and element-summary data

RETRY_STATUSES = {429, 500, 502, 503, 504}


class FPLError(RuntimeError):
    """The FPL API failed after retries, or returned an unexpected response."""


class FPLNotFound(FPLError):
    """The team, league or gameweek doesn't exist (HTTP 404)."""


class FPLClient:
    def __init__(
        self,
        cache: DiskCache | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 10.0,
        max_retries: int = 3,
        backoff: float = 1.0,
        min_interval: float = 0.25,
        bulk_interval: float = 1.0,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self.cache = cache or DiskCache()
        self.http = httpx.Client(
            base_url=BASE_URL,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            timeout=timeout,
            transport=transport,
            follow_redirects=True,
        )
        self.max_retries = max_retries
        self.backoff = backoff
        self.min_interval = min_interval
        self.bulk_interval = bulk_interval
        self._sleep = sleep
        self._monotonic = monotonic
        self._now = now
        self._last_request: float | None = None
        self.network_calls = 0  # handy for tests and for logging call budgets

    def close(self) -> None:
        self.http.close()

    def __enter__(self) -> "FPLClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ---- shared, per-gameweek data -------------------------------------------------

    def bootstrap(self) -> dict[str, Any]:
        key = "bootstrap-static"
        if (cached := self.cache.get(key)) is not None:
            return cached
        data = self._get_json("bootstrap-static/")
        self.cache.set(key, data, ttl=SHARED_TTL, expires_at=self._deadline_ts(data))
        return data

    def fixtures(self) -> list[dict[str, Any]]:
        key = "fixtures"
        if (cached := self.cache.get(key)) is not None:
            return cached
        data = self._get_json("fixtures/")
        self.cache.set(key, data, ttl=SHARED_TTL, expires_at=self._deadline_ts(self.bootstrap()))
        return data

    def event_live(self, gw: int) -> dict[str, Any]:
        key = f"event-{gw}-live"
        if (cached := self.cache.get(key)) is not None:
            return cached
        data = self._get_json(f"event/{gw}/live/")
        if self._is_final(gw):
            self.cache.set(key, data)  # final points never change
        else:
            self.cache.set(key, data, ttl=LIVE_IN_PROGRESS_TTL)
        return data

    # ---- per-player data (use sparingly; never inside a request handler) -------------

    def element_summary(self, element_id: int) -> dict[str, Any]:
        return self._short_lived(f"element-summary-{element_id}", f"element-summary/{element_id}/")

    # ---- manager data ----------------------------------------------------------------

    def entry(self, entry_id: int) -> dict[str, Any]:
        return self._short_lived(f"entry-{entry_id}", f"entry/{entry_id}/")

    def entry_history(self, entry_id: int) -> dict[str, Any]:
        return self._short_lived(f"entry-{entry_id}-history", f"entry/{entry_id}/history/")

    def entry_transfers(self, entry_id: int) -> list[dict[str, Any]]:
        return self._short_lived(f"entry-{entry_id}-transfers", f"entry/{entry_id}/transfers/")

    def entry_picks(self, entry_id: int, gw: int) -> dict[str, Any]:
        key = f"entry-{entry_id}-event-{gw}-picks"
        if (cached := self.cache.get(key)) is not None:
            return cached
        data = self._get_json(f"entry/{entry_id}/event/{gw}/picks/")
        # Picks for a finished GW are fixed; for the current GW they can't change after the deadline
        # either, but auto-subs land as the GW is played, so keep those short-lived.
        if self._is_final(gw):
            self.cache.set(key, data)
        else:
            self.cache.set(key, data, ttl=SHORT_TTL)
        return data

    def many_entry_picks(self, entry_ids: Iterable[int], gw: int) -> dict[int, dict[str, Any] | None]:
        """Bulk fetch (e.g. rivals' picks), throttled to one live request per `bulk_interval`.

        A rival whose picks are missing (404, e.g. joined after that GW) maps to None.
        """
        results: dict[int, dict[str, Any] | None] = {}
        for entry_id in entry_ids:
            try:
                results[entry_id] = self._with_interval(self.bulk_interval, self.entry_picks, entry_id, gw)
            except FPLNotFound:
                results[entry_id] = None
        return results

    # ---- leagues -----------------------------------------------------------------------

    def league_standings(self, league_id: int, page: int = 1) -> dict[str, Any]:
        return self._short_lived(
            f"league-{league_id}-standings-p{page}",
            f"leagues-classic/{league_id}/standings/",
            params={"page_standings": page},
        )

    def league_standings_all(self, league_id: int, max_pages: int = 20) -> list[dict[str, Any]]:
        """Every standings page until `has_next` is false (capped, 50 managers per page)."""
        pages: list[dict[str, Any]] = []
        for page in range(1, max_pages + 1):
            data = self._with_interval(self.bulk_interval, self.league_standings, league_id, page)
            pages.append(data)
            if not data.get("standings", {}).get("has_next"):
                break
        return pages

    # ---- internals -----------------------------------------------------------------------

    def _short_lived(self, key: str, path: str, params: dict[str, Any] | None = None) -> Any:
        if (cached := self.cache.get(key)) is not None:
            return cached
        data = self._get_json(path, params=params)
        self.cache.set(key, data, ttl=SHORT_TTL)
        return data

    def _with_interval(self, interval: float, fn: Callable[..., Any], *args: Any) -> Any:
        saved = self.min_interval
        self.min_interval = max(saved, interval)
        try:
            return fn(*args)
        finally:
            self.min_interval = saved

    def _events(self, bootstrap: dict[str, Any]) -> list[Event]:
        return [Event.model_validate(e) for e in bootstrap.get("events", [])]

    def _deadline_ts(self, bootstrap: dict[str, Any]) -> float | None:
        deadline = next_deadline(self._events(bootstrap), self._now())
        return deadline.timestamp() if deadline else None

    def _is_final(self, gw: int) -> bool:
        for event in self._events(self.bootstrap()):
            if event.id == gw:
                return event.finished and event.data_checked
        return False

    def _throttle(self) -> None:
        if self._last_request is not None:
            wait = self.min_interval - (self._monotonic() - self._last_request)
            if wait > 0:
                self._sleep(wait)
        self._last_request = self._monotonic()

    def _get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            if attempt:
                self._sleep(self._retry_delay(attempt, last_error))
            self._throttle()
            self.network_calls += 1
            try:
                response = self.http.get(path, params=params)
            except httpx.TransportError as exc:
                log.warning("FPL %s failed (%s), attempt %d", path, exc, attempt + 1)
                last_error = exc
                continue

            if response.status_code == 404:
                raise FPLNotFound(f"FPL has no data at {path}")
            if response.status_code in RETRY_STATUSES:
                log.warning("FPL %s returned %d, attempt %d", path, response.status_code, attempt + 1)
                last_error = _StatusError(response)
                continue
            if response.status_code >= 400:
                raise FPLError(f"FPL {path} returned HTTP {response.status_code}")
            try:
                return response.json()
            except ValueError as exc:
                # FPL serves an HTML/text page while "the game is being updated".
                raise FPLError(f"FPL {path} did not return JSON (the game may be updating)") from exc

        raise FPLError(f"FPL {path} failed after {self.max_retries + 1} attempts: {last_error}")

    def _retry_delay(self, attempt: int, error: Exception | None) -> float:
        if isinstance(error, _StatusError):
            retry_after = error.response.headers.get("Retry-After", "")
            if retry_after.isdigit():
                return min(float(retry_after), 60.0)
        return self.backoff * 2 ** (attempt - 1)


class _StatusError(Exception):
    def __init__(self, response: httpx.Response) -> None:
        super().__init__(f"HTTP {response.status_code}")
        self.response = response
