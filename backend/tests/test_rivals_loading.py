"""Rivals load in the background: the team screen answers at once and reports progress."""

import time
from collections.abc import Iterator
from datetime import datetime
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.main import app, get_service, set_service
from app.api.service import PlannerService
from app.fpl.cache import DiskCache
from app.fpl.client import FPLClient
from tests.fakes import FakeFPL, fixture_routes

TEAM, LEAGUE = 5179483, 1883627


@pytest.fixture
def cold(manifest: dict[str, Any], snapshot_time: datetime, tmp_path) -> Iterator[tuple[TestClient, FakeFPL]]:
    """A fresh service with an empty cache, so nothing about the rivals is loaded yet."""
    fake = FakeFPL(fixture_routes(manifest))
    client = FPLClient(
        DiskCache(tmp_path, clock=lambda: snapshot_time.timestamp()),
        transport=httpx.MockTransport(fake), sleep=lambda _: None, now=lambda: snapshot_time,
    )
    previous = get_service()
    set_service(PlannerService(client, now=lambda: snapshot_time))
    yield TestClient(app), fake
    set_service(previous)


def _wait_ready(api: TestClient, params: dict) -> dict:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        body = api.get("/api/rivals", params=params).json()
        if body["ready"]:
            return body
        time.sleep(0.05)
    raise AssertionError("rivals never finished loading")


def test_team_answers_before_rivals_load_then_fills_in(cold) -> None:
    api, _ = cold
    first = api.get(f"/api/team/{TEAM}", params={"league": LEAGUE}).json()
    rivals = first["rivals"]
    assert rivals["league_id"] == LEAGUE and rivals["total"] == 2
    if not rivals["ready"]:  # the usual case: nothing cached yet
        assert all(l["rivals_avg"] is None for l in first["lineups"])
        assert first["standing"]["n_rivals"] == 2  # known from the standings already
    progress = _wait_ready(api, {"team": TEAM, "league": LEAGUE})
    assert progress == {"league_id": LEAGUE, "loaded": 2, "total": 2, "ready": True}
    second = api.get(f"/api/team/{TEAM}", params={"league": LEAGUE}).json()
    assert second["rivals"]["ready"] is True
    assert all(l["rivals_avg"] is not None for l in second["lineups"])


def test_pasting_a_league_link_starts_loading_rivals(cold) -> None:
    api, fake = cold
    api.get("/api/resolve", params={"input": f"fantasy.premierleague.com/leagues/{LEAGUE}/standings/c"})
    _wait_ready(api, {"team": TEAM, "league": LEAGUE})
    api.get(f"/api/team/{TEAM}", params={"league": LEAGUE, "wait_rivals": True})
    picks = [r.url.path for r in fake.requests if r.url.path.endswith("/picks/")]
    assert picks and len(picks) == len(set(picks))  # every squad fetched once, never twice


def test_no_league_is_ready_at_once(cold) -> None:
    api, _ = cold
    assert api.get("/api/rivals", params={"team": TEAM, "league": 0}).json() == {"league_id": 0, "loaded": 0, "total": 0, "ready": True}


def test_plans_wait_for_rivals(cold) -> None:
    api, _ = cold
    body = api.get("/api/plans", params={"team": TEAM, "league": LEAGUE, "horizon": 1}).json()
    assert body["standing"]["n_rivals"] == 2  # plans always use the full rival set


def test_expired_rivals_reload_in_the_background(cold) -> None:
    """A prefetch that finished long ago doesn't count: expired picks load in the background,
    not inside the request (review finding)."""
    import app.api.service as service_mod

    api, fake = cold
    _wait_ready(api, {"team": TEAM, "league": LEAGUE})
    svc = get_service()
    job, started = svc._jobs[LEAGUE]
    svc._jobs[LEAGUE] = (job, started - service_mod.PREFETCH_FRESH - 1)  # long finished
    for f in svc.client.cache.root.glob("entry-*-event-*-picks.json"):
        f.unlink()  # the picks expired
    body = api.get(f"/api/team/{TEAM}", params={"league": LEAGUE}).json()
    assert body["rivals"]["ready"] is False  # answered at once; loading in the background
    _wait_ready(api, {"team": TEAM, "league": LEAGUE})


def test_what_if_does_not_wait_for_rivals(cold) -> None:
    api, fake = cold
    r = api.post("/api/what-if", json={"team": TEAM, "league": LEAGUE, "horizon": 2}).json()
    assert r["problems"] == []
    rival_picks = [q.url.path for q in fake.requests if q.url.path.endswith("/picks/") and f"/entry/{TEAM}/" not in q.url.path]
    assert rival_picks == []


def test_identical_plan_requests_solve_once(cold, monkeypatch) -> None:
    import threading

    import app.api.service as service_mod

    api, _ = cold
    _wait_ready(api, {"team": TEAM, "league": LEAGUE})
    calls = []
    real = service_mod.make_plans
    monkeypatch.setattr(service_mod, "make_plans", lambda *a, **k: calls.append(1) or real(*a, **k))
    svc = get_service()
    threads = [threading.Thread(target=svc.plans, args=(TEAM, LEAGUE, "protect", 2, 0)) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(calls) == 1
