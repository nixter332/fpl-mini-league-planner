"""A team created since the last deadline has no picks yet: say when it starts, not "not found"."""

from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from tests.conftest import load_fixture

NEW_TEAM = 11326400


@pytest.fixture
def new_team_api(manifest: dict[str, Any], snapshot_time, tmp_path):
    from app.api import main
    from app.api.service import PlannerService
    from app.fpl.cache import DiskCache
    from app.fpl.client import FPLClient
    from tests.fakes import FakeFPL, fixture_routes

    routes = fixture_routes(manifest)
    entry = dict(load_fixture(manifest["files"]["entry"]))
    entry.update(id=NEW_TEAM, started_event=manifest["latest_started_gw"] + 1, current_event=None)
    routes[f"/api/entry/{NEW_TEAM}/"] = entry  # the team exists, but has no picks for the started GW
    client = FPLClient(
        DiskCache(tmp_path, clock=lambda: snapshot_time.timestamp()),
        transport=httpx.MockTransport(FakeFPL(routes)), sleep=lambda _: None, now=lambda: snapshot_time,
    )
    previous = main._service  # the session-wide `api` fixture's service; put it back afterwards
    main.set_service(PlannerService(client, now=lambda: snapshot_time))
    yield TestClient(main.app)
    main.set_service(previous)


def test_a_new_team_says_when_it_starts(new_team_api: TestClient, manifest: dict[str, Any]) -> None:
    starts = manifest["latest_started_gw"] + 1
    r = new_team_api.get(f"/api/team/{NEW_TEAM}")
    assert r.status_code == 404
    body = r.json()
    assert body["code"] == "not_started" and body["starts_gw"] == starts
    assert f"GW{starts}" in body["detail"] and "couldn't find" not in body["detail"]
    assert body["deadline"]  # the frontend shows it in the visitor's time zone
    plans = new_team_api.get("/api/plans", params={"team": NEW_TEAM, "league": 0})
    assert plans.status_code == 404 and plans.json()["code"] == "not_started"


def test_a_team_that_doesnt_exist_is_still_not_found(new_team_api: TestClient) -> None:
    r = new_team_api.get("/api/team/999999999")
    assert r.status_code == 404 and "couldn't find" in r.json()["detail"]
