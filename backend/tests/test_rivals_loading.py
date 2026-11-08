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
