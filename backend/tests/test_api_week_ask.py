"""The "This week" page and the plan questions (keep / ban), on the saved fixtures."""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.service import ban_threshold

TEAM, LEAGUE = 5179483, 1883627
BASE = {"team": TEAM, "league": LEAGUE, "strategy": "protect", "horizon": 4, "max_hits": 0}
BOOTSTRAP = json.loads((Path(__file__).parent / "fixtures" / "bootstrap-static.json").read_text(encoding="utf-8"))


def test_yellow_card_ban_warning() -> None:
    assert ban_threshold(4, 11) == 5  # one more before GW19 is a ban
    assert ban_threshold(4, 20) is None  # that rule has ended
    assert ban_threshold(9, 25) == 10
    assert ban_threshold(9, 33) is None
    assert ban_threshold(3, 11) is None and ban_threshold(5, 11) is None


def test_week_page(api: TestClient) -> None:
    api.get(f"/api/team/{TEAM}", params={"league": LEAGUE, "wait_rivals": True})  # rivals loaded
    body = api.get("/api/week", params={"team": TEAM, "league": LEAGUE}).json()
    assert body["gw"] == 11 and 1 <= body["last_gw"] < body["gw"]  # the last fully finished gameweek
    players = body["players"]

    # Top transfers: straight from FPL's counts, biggest first.
    by_id = {e["id"]: e for e in BOOTSTRAP["elements"]}
    ins = [m["count"] for m in body["top_in"]]
    assert ins == sorted(ins, reverse=True) and len(ins) == 5
    assert ins[0] == max(e["transfers_in_event"] for e in BOOTSTRAP["elements"])
    for m in body["top_out"]:
        assert m["count"] == by_id[m["player"]]["transfers_out_event"]

    # Ticker: every club, 5 gameweeks, easiest run first.
    assert len(body["ticker"]) == 20
    avgs = [r["avg_difficulty"] for r in body["ticker"]]
    assert avgs == sorted(avgs)
    assert all(len(r["gws"]) == 5 for r in body["ticker"])

    # Flags: every doubtful player in my squad is listed; all flagged players are in `players`.
    squad = api.get(f"/api/team/{TEAM}", params={"league": LEAGUE}).json()
    doubtful = {int(pid) for pid, p in squad["players"].items() if p["doubtful"]}
    mine = {f["player"] for f in body["flags"] if f["mine"]}
    assert doubtful <= mine
    for f in body["flags"]:
        assert str(f["player"]) in players
        assert f["news"] or f["ban_at"]
        if not f["mine"]:
            assert f["rivals_owned"] >= 1

    # Team of the week: 11 players from the last finished gameweek.
    assert len(body["dream_team"]) == 11
    assert all(d["points"] > 0 and str(d["player"]) in players for d in body["dream_team"])


def test_ban_gives_the_next_best_plan(api: TestClient) -> None:
    best = api.get("/api/plans", params=BASE).json()["plans"][0]
    bought = [m["player_in"] for m in best["gameweeks"][0]["moves"]]
    assert bought, "the fixture squad's best plan makes a transfer"
    other = api.get("/api/plans", params={**BASE, "ban": str(bought[0])}).json()["plans"]
    for plan in other:
        assert all(m["player_in"] != bought[0] for g in plan["gameweeks"] for m in g["moves"])
    assert other[0]["xpts_gain"] <= best["xpts_gain"] + 0.05  # a constraint can't beat the free optimum


def test_keep_never_sells_the_player(api: TestClient) -> None:
    best = api.get("/api/plans", params=BASE).json()["plans"][0]
    sold = [m["player_out"] for m in best["gameweeks"][0]["moves"]]
    assert sold
    kept = api.get("/api/plans", params={**BASE, "keep": str(sold[0])}).json()["plans"]
    for plan in kept:
        assert all(m["player_out"] != sold[0] for g in plan["gameweeks"] for m in g["moves"])
    assert kept[0]["xpts_gain"] <= best["xpts_gain"] + 0.05


def test_keep_and_ban_are_validated(api: TestClient) -> None:
    not_mine = next(e["id"] for e in BOOTSTRAP["elements"] if e["id"] not in {int(p) for p in api.get(f"/api/team/{TEAM}", params={"league": 0}).json()["players"]})
    r = api.get("/api/plans", params={**BASE, "keep": str(not_mine)})
    assert r.status_code == 400 and "in your squad" in r.json()["detail"]
    assert api.get("/api/plans", params={**BASE, "ban": "1,2,3,4"}).status_code == 422
    assert api.get("/api/plans", params={**BASE, "keep": "abc"}).status_code == 422
