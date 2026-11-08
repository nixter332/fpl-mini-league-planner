"""Rate limits that protect the Claude credit and the free server."""

import asyncio
from pathlib import Path

from starlette.requests import Request

from app.api.limits import RateLimiter, client_key
from app.explain.explainer import Explainer
from app.fpl.cache import DiskCache
from tests.fakes import FakeClaude


class Clock:
    def __init__(self) -> None:
        self.t = 1_000_000.0

    def __call__(self) -> float:
        return self.t


def test_sliding_window_per_key() -> None:
    clock = Clock()
    limiter = RateLimiter(2, 60, clock)
    assert limiter.allow("a") and limiter.allow("a") and not limiter.allow("a")
    assert limiter.allow("b")  # someone else isn't affected
    clock.t += 60
    assert limiter.allow("a")


def test_client_key_uses_the_first_forwarded_ip() -> None:
    def req(headers: dict[str, str]) -> Request:
        return Request({"type": "http", "headers": [(k.encode(), v.encode()) for k, v in headers.items()], "client": ("10.0.0.1", 1)})

    assert client_key(req({"x-forwarded-for": "203.0.113.7, 10.1.1.1"})) == "203.0.113.7"
    assert client_key(req({})) == "10.0.0.1"


def test_daily_claude_cap(tmp_path: Path) -> None:
    clock = Clock()
    fake = FakeClaude({"why": "Saka is in.", "watch_out": "Saka is out."})
    explainer = Explainer(fake, DiskCache(tmp_path), daily_calls=2, clock=clock)
    run = lambda i: asyncio.run(explainer.explain({"plan": i, "players": ["Saka"]}, {"Saka"}))
    assert run(1) is not None and run(2) is not None
    assert run(3) is None  # cap reached: no call made
    assert len(fake.calls) == 2
    assert run(1) is not None  # cached reasons still show
    clock.t += 24 * 3600
    assert run(3) is not None  # a new day
