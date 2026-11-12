"""The rivals page, the captain options and the gameweek review, on the saved fixtures."""

import copy
from datetime import datetime
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

TEAM, LEAGUE = 5179483, 1883627
Q = {"team": TEAM, "league": LEAGUE}


def test_league_view(api: TestClient) -> None:
    team = api.get(f"/api/team/{TEAM}", params={"league": LEAGUE, "wait_rivals": True}).json()
    body = api.get("/api/league", params=Q).json()
    assert body["ready"] and body["gw"] == 11 and body["league"]["id"] == LEAGUE
    rows = body["rows"]
    assert len(rows) == 3 and [r["rank"] for r in rows] == sorted(r["rank"] for r in rows)
    me = next(r for r in rows if r["is_me"])
    assert me["entry"] == TEAM and me["xpts"] == team["lineups"][0]["xpts"] and me["captain"] == team["lineups"][0]["captain"]
    assert sorted(r["projected_rank"] for r in rows) == [1, 2, 3]
    by_projection = sorted(rows, key=lambda r: -r["projected_total"])
    assert [r["projected_rank"] for r in by_projection] == [1, 2, 3]
    squad = set(team["squad"])
    for r in rows:
        assert r["projected_total"] == pytest.approx(r["total"] + r["xpts"], abs=0.06)
        if not r["is_me"]:
            assert r["captain"] is not None and 0 <= r["shared"] <= 15
            assert not set(r["differentials"]) & squad  # theirs, not mine
            assert set(r["my_differentials"]) <= squad
            assert all(str(p) in body["players"] for p in r["differentials"] + r["my_differentials"])


def test_league_view_without_a_league(api: TestClient) -> None:
    body = api.get("/api/league", params={"team": TEAM, "league": 0}).json()
    assert body["league"] is None and body["rows"] == []


def test_captain_options(api: TestClient) -> None:
    team = api.get(f"/api/team/{TEAM}", params={"league": LEAGUE, "wait_rivals": True}).json()
    caps = api.get("/api/week", params=Q).json()["captains"]
    assert len(caps) == 4
    assert [c["xpts"] for c in caps] == sorted((c["xpts"] for c in caps), reverse=True)
    assert caps[0]["player"] == team["lineups"][0]["captain"]
    assert all(c["player"] in team["lineups"][0]["starting"] for c in caps)


def test_review_waits_for_the_gameweek_to_finish(api: TestClient) -> None:
    body = api.get("/api/review", params=Q).json()  # the snapshot was taken during GW10
    assert body["available"] is False and "GW10 is still being played" in body["message"]


@pytest.fixture(scope="module")
def api_after_gw10(manifest: dict[str, Any], snapshot_time: datetime, tmp_path_factory: pytest.TempPathFactory):
    """The same fixtures, with GW10 marked as finished."""
    import app.api.main as main
    from app.api.main import app, set_service
    from app.api.service import PlannerService
    from app.fpl.cache import DiskCache
    from app.fpl.client import FPLClient
    from tests.fakes import FakeFPL, fixture_routes

    previous = main._service  # the shared fixture service, put back afterwards
    routes = fixture_routes(manifest)
    bootstrap = copy.deepcopy(routes["/api/bootstrap-static/"])
    gw10 = next(e for e in bootstrap["events"] if e["id"] == 10)
    gw10.update(finished=True, data_checked=True)
    routes["/api/bootstrap-static/"] = bootstrap
    client = FPLClient(
        DiskCache(tmp_path_factory.mktemp("cache-gw10"), clock=lambda: snapshot_time.timestamp()),
        transport=httpx.MockTransport(FakeFPL(routes)), sleep=lambda _: None, now=lambda: snapshot_time,
    )
    set_service(PlannerService(client, now=lambda: snapshot_time))
    yield TestClient(app)
    set_service(previous)


def test_review_of_a_finished_gameweek(api_after_gw10: TestClient, manifest: dict[str, Any]) -> None:
    from tests.conftest import load_fixture

    api = api_after_gw10
    api.get(f"/api/team/{TEAM}", params={"league": LEAGUE, "wait_rivals": True})
    body = api.get("/api/review", params=Q).json()
    assert body["available"] and body["gw"] == 10
    picks = load_fixture(manifest["files"]["picks"])
    live = {el["id"]: el["stats"] for el in load_fixture(manifest["files"]["event_live"]["10"])["elements"]}
    mine = picks["entry_history"]["points"] - picks["entry_history"]["event_transfers_cost"]
    assert body["points"] == mine
    captain = next(p["element"] for p in picks["picks"] if p["multiplier"] > 1)
    assert body["captain"] == {"player": captain, "points": live[captain]["total_points"], "projected": body["captain"]["projected"]}
    starters = [p["element"] for p in picks["picks"] if p["multiplier"] > 0]
    assert body["best_captain"]["points"] == max(live[p]["total_points"] for p in starters)
    assert 20 < body["projected"] < 90  # a plausible XI + captain projection made before the deadline
    for p in body["over"]:
        assert p["points"] > p["projected"] and p["player"] in starters
    for p in body["under"]:
        assert p["points"] < p["projected"] and p["player"] in starters
    assert len(body["rivals"]) == 2
    for name, rival in zip(sorted(manifest["files"]["rival_picks"]), sorted(body["rivals"], key=lambda r: r["points"])):
        assert rival["swing"] == mine - rival["points"]
    theirs = sorted(load_fixture(n)["entry_history"]["points"] - load_fixture(n)["entry_history"]["event_transfers_cost"] for n in manifest["files"]["rival_picks"].values())
    assert sorted(r["points"] for r in body["rivals"]) == theirs
