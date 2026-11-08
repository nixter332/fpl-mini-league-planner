"""A bare number that is both a team ID and a league ID: the user is asked which they meant."""

from datetime import datetime
from typing import Any

import httpx
from fastapi.testclient import TestClient

from app.api.main import app, get_service, set_service
from app.api.service import PlannerService
from app.fpl.cache import DiskCache
from app.fpl.client import FPLClient
from tests.fakes import FakeFPL, fixture_routes

TEAM, LEAGUE = 5179483, 1883627


def test_number_that_is_both_team_and_league(manifest: dict[str, Any], snapshot_time: datetime, tmp_path) -> None:
    routes = fixture_routes(manifest)
    # Pretend a team also has the league's number.
    routes[f"/api/entry/{LEAGUE}/"] = routes[f"/api/entry/{TEAM}/"]
    client = FPLClient(
        DiskCache(tmp_path, clock=lambda: snapshot_time.timestamp()),
        transport=httpx.MockTransport(FakeFPL(routes)), sleep=lambda _: None, now=lambda: snapshot_time,
    )
    previous = get_service()
    set_service(PlannerService(client, now=lambda: snapshot_time))
    try:
        body = TestClient(app).get("/api/resolve", params={"input": str(LEAGUE)}).json()
    finally:
        set_service(previous)
    assert body["type"] == "choice" and body["id"] == LEAGUE
    assert body["team_name"] and body["manager_name"] and body["league_name"]
    assert body["members"]  # ready if they pick the league
