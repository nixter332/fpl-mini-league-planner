"""Chips through the API, on Nikhil's saved squad (Free Hit and Bench Boost left until GW19)."""

from fastapi.testclient import TestClient

TEAM, LEAGUE = 5179483, 1883627
BASE = {"team": TEAM, "league": LEAGUE, "strategy": "protect", "horizon": 3, "max_hits": 0}


def test_plans_list_chips_left(api: TestClient) -> None:
    body = api.get("/api/plans", params=BASE).json()
    first_half = {(c["name"], c["stop"]) for c in body["chips_left"] if c["stop"] == 19}
    assert first_half == {("freehit", 19), ("bboost", 19)}
    assert body["auto_chips"] is True and body["wildcard_gw"] is None
    for plan in body["plans"]:
        chips = [g for g in plan["gameweeks"] if g["chip"]]
        assert all(g["chip"] == "bboost" and g["chip_xpts"] > 0 for g in chips)
        assert plan["chip_xpts"] == sum(g["chip_xpts"] for g in chips)


def test_free_hit_this_week(api: TestClient) -> None:
    body = api.get("/api/plans", params={**BASE, "freehit": 11}).json()
    assert body["freehit_gw"] == 11
    first = body["plans"][0]["gameweeks"][0]
    assert first["chip"] == "freehit" and first["hits"] == 0 and first["moves"]
    assert "Free Hit in GW11" in body["plans"][0]["summary"]


def test_chips_switched_off(api: TestClient) -> None:
    body = api.get("/api/plans", params={**BASE, "chips": False}).json()
    assert all(g["chip"] is None for p in body["plans"] for g in p["gameweeks"])
    assert all(p["chip_xpts"] == 0 for p in body["plans"])


def test_used_or_out_of_range_chips_are_refused(api: TestClient) -> None:
    r = api.get("/api/plans", params={**BASE, "wildcard": 11})  # played in GW6
    assert r.status_code == 400 and "don't have a Wildcard" in r.json()["detail"]
    r = api.get("/api/plans", params={**BASE, "freehit": 20})
    assert r.status_code == 400 and "isn't in this plan" in r.json()["detail"]

