"""Analysis, what-if and the player list through the API (saved fixtures)."""

from fastapi.testclient import TestClient

TEAM, LEAGUE = 5179483, 1883627


def test_analysis(api: TestClient) -> None:
    body = api.get("/api/analysis", params={"team": TEAM, "league": LEAGUE, "strategy": "protect", "horizon": 4}).json()
    assert len(body["spots"]) == 15 and body["gws"][0] == 11
    levels = {s["level"] for s in body["spots"]}
    assert "red" in levels and "ok" in levels
    for spot in body["spots"]:
        assert str(spot["player"]) in body["players"]
        for r in spot["replacements"]:
            assert str(r["player"]) in body["players"]


def test_what_if_round_trip(api: TestClient) -> None:
    analysis = api.get("/api/analysis", params={"team": TEAM, "league": LEAGUE, "horizon": 4}).json()
    spot = next(s for s in analysis["spots"] if s["replacements"])
    move = {"gw": 11, "out": spot["player"], "into": spot["replacements"][0]["player"]}
    base = api.post("/api/what-if", json={"team": TEAM, "league": LEAGUE, "horizon": 4}).json()
    assert base["problems"] == [] and base["xpts_gain"] == 0
    r = api.post("/api/what-if", json={"team": TEAM, "league": LEAGUE, "horizon": 4, "moves": [move]}).json()
    assert r["problems"] == []
    assert r["weeks"][0]["moves"][0]["player_in"] == move["into"]
    assert r["xpts_gain"] == round(r["xpts"] - r["no_transfers_xpts"], 2)
    # The analysis promised this swap's gain; the what-if must agree (same rules, same points).
    assert r["xpts_gain"] >= spot["replacements"][0]["gain"] - 0.6  # bench weighting is the only difference


def test_what_if_reports_illegal_moves(api: TestClient) -> None:
    squad = set(api.post("/api/what-if", json={"team": TEAM, "horizon": 2}).json()["weeks"][0]["squad"])
    outsider = next(int(p) for p in api.get("/api/players", params={"team": TEAM}).json()["players"] if int(p) not in squad)
    r = api.post("/api/what-if", json={"team": TEAM, "horizon": 2, "moves": [{"gw": 11, "out": outsider, "into": min(squad)}]}).json()
    assert r["problems"] and "isn't in your squad" in r["problems"][0]["message"]
    bad = api.post("/api/what-if", json={"team": TEAM, "moves": [{"gw": 11, "out": 1}]})
    assert bad.status_code == 422


def test_players_list(api: TestClient) -> None:
    body = api.get("/api/players", params={"team": TEAM, "league": LEAGUE}).json()
    assert len(body["players"]) > 500 and body["gws"]


def test_replacement_reason(api: TestClient, tmp_path) -> None:
    from app.api import schemas as s
    from app.api.main import get_service, set_explainer
    from app.explain.check import check
    from app.explain.explainer import Explainer, facts_text
    from app.explain.summary import build_replacement_summary
    from app.fpl.cache import DiskCache
    from tests.fakes import FakeClaude

    body = api.get("/api/analysis", params={"team": TEAM, "league": LEAGUE, "horizon": 4}).json()
    resp = s.AnalysisResponse.model_validate(body)
    spot = next(sp for sp in resp.spots if sp.replacements)
    facts = build_replacement_summary(resp, spot)
    top = facts["options_best_first"][0]
    # A faithful reason passes the trust check; the facts carry the team gain and both players.
    why = f"{top['name']} adds {top['team_points_gain']} expected points to your team over {facts['gameweeks']}."
    assert check(why, "Rotation risk.", facts_text(facts), get_service().known_names()) == []

    fake = FakeClaude({"why": why, "watch_out": "Rotation risk."})
    set_explainer(Explainer(fake, DiskCache(tmp_path)))
    try:
        r = api.get("/api/analysis/explain", params={"team": TEAM, "league": LEAGUE, "horizon": 4, "player": spot.player}).json()
    finally:
        set_explainer(None)
    assert r == {"player": spot.player, "status": "ok", "why": why, "watch_out": "Rotation risk."}
    assert "best affordable replacements" in fake.calls[0]["system"]
