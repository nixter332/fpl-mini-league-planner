"""API routes on the saved fixtures (fake FPL server, no network)."""

from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.main import app, set_service
from app.api.service import PlannerService
from app.fpl.cache import DiskCache
from app.fpl.client import FPLClient
from tests.fakes import FakeFPL, fixture_routes

TEAM, LEAGUE = 5179483, 1883627


@pytest.fixture(scope="module")
def api(manifest: dict[str, Any], snapshot_time: datetime, tmp_path_factory: pytest.TempPathFactory) -> Iterator[TestClient]:
    fake = FakeFPL(fixture_routes(manifest))
    client = FPLClient(
        DiskCache(tmp_path_factory.mktemp("cache"), clock=lambda: snapshot_time.timestamp()),
        transport=httpx.MockTransport(fake), sleep=lambda _: None, now=lambda: snapshot_time,
    )
    set_service(PlannerService(client, now=lambda: snapshot_time))
    yield TestClient(app)
    set_service(None)


def test_resolve_team_id_and_links(api: TestClient) -> None:
    assert api.get("/api/resolve", params={"input": str(TEAM)}).json() == {
        "type": "team", "id": TEAM, "league_name": None, "members": [], "more_members": False,
    }
    body = api.get("/api/resolve", params={"input": f"https://fantasy.premierleague.com/entry/{TEAM}/history"}).json()
    assert body["type"] == "team"


def test_resolve_league_lists_members(api: TestClient) -> None:
    body = api.get("/api/resolve", params={"input": f"fantasy.premierleague.com/leagues/{LEAGUE}/standings/c"}).json()
    assert body["type"] == "league" and body["league_name"]
    assert TEAM in {m["entry"] for m in body["members"]}
    assert [m["rank"] for m in body["members"]] == sorted(m["rank"] for m in body["members"])


def test_bad_input_is_a_friendly_400(api: TestClient) -> None:
    r = api.get("/api/resolve", params={"input": "https://example.com/team/1"})
    assert r.status_code == 400
    assert "We accept" in r.json()["detail"]


def test_unknown_team_is_a_404(api: TestClient) -> None:
    r = api.get("/api/resolve", params={"input": "999999999"})
    assert r.status_code == 404
    assert "couldn't find" in r.json()["detail"]


def test_team_screen(api: TestClient) -> None:
    body = api.get(f"/api/team/{TEAM}").json()  # no league given: the smallest private league
    assert body["standing"]["league"]["id"] == LEAGUE
    assert body["leagues"][0]["id"] == LEAGUE
    sizes = [l["size"] for l in body["leagues"]]
    assert sizes == sorted(sizes)
    assert body["free_transfers"] == 2 and body["bank"] == 11
    assert [g["id"] for g in body["gameweeks"]] == [11, 12, 13, 14, 15]
    assert len(body["squad"]) == 15
    for lineup in body["lineups"]:
        assert len(lineup["starting"]) == 11 and len(lineup["bench"]) == 4
        assert lineup["captain"] in lineup["starting"]
        assert lineup["rivals_avg"] is not None
        assert lineup["edge"] == pytest.approx(lineup["xpts"] - lineup["rivals_avg"], abs=0.02)
    players = body["players"]
    assert set(map(int, players)) == set(body["squad"])
    haaland = players["411"]
    assert haaland["club"] == "MCI" and len(haaland["gws"]) == 5 and haaland["gws"][0]["fixture"] != "—"
    assert body["clubs"]["MCI"]["kit"]["body"].startswith("#")
    assert any("deadline" in f for f in body["facts"])


def test_team_screen_without_league(api: TestClient) -> None:
    body = api.get(f"/api/team/{TEAM}", params={"league": 0}).json()
    assert body["standing"] is None
    assert all(l["rivals_avg"] is None for l in body["lineups"])


@pytest.mark.parametrize("strategy", ["protect", "balanced", "risky"])
def test_plans(api: TestClient, strategy: str) -> None:
    body = api.get("/api/plans", params={"team": TEAM, "league": LEAGUE, "strategy": strategy, "horizon": 4, "max_hits": 1}).json()
    assert body["gws"] == [11, 12, 13, 14]
    assert len(body["plans"]) == 3
    assert body["captain_note"]
    for plan in body["plans"]:
        assert plan["xpts_gain"] >= -1e-6  # do no harm
        assert plan["tag"] in {"free", "hit", "roll"}
        assert len(plan["after"]["starting"]) == 11
        for gw in plan["gameweeks"]:
            for move in gw["moves"]:
                out, inn = body["players"][str(move["player_out"])], body["players"][str(move["player_in"])]
                assert out["position"] == inn["position"]
        assert plan["head_to_head"] is not None
        for t in plan["threats"]:
            assert t["player"] not in plan["after"]["starting"] + plan["after"]["bench"]


def test_plans_are_cached(api: TestClient) -> None:
    params = {"team": TEAM, "league": LEAGUE, "strategy": "protect", "horizon": 3, "max_hits": 0}
    first = api.get("/api/plans", params=params).json()
    again = api.get("/api/plans", params=params).json()
    assert first == again


def test_plan_params_are_validated(api: TestClient) -> None:
    assert api.get("/api/plans", params={"team": TEAM, "strategy": "chase"}).status_code == 422
    assert api.get("/api/plans", params={"team": TEAM, "horizon": 9}).status_code == 422


def test_default_league_is_the_first_private_one() -> None:
    from app.api.schemas import LeagueInfo

    leagues = [LeagueInfo(id=7, name="Office"), LeagueInfo(id=9, name="Family")]
    assert PlannerService._pick_league(None, leagues) == 7
    assert PlannerService._pick_league(0, leagues) is None  # 0 = no league
    assert PlannerService._pick_league(9, leagues) == 9
    assert PlannerService._pick_league(None, []) is None
