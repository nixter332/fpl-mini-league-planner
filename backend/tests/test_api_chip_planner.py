"""Chip planner (phase 7): /api/chips, /api/chips/explain, and choosing a Bench Boost week in Plans."""

import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api import schemas as s
from app.api.main import set_explainer
from app.explain.check import numbers_in
from app.explain.explainer import Explainer, facts_text
from app.explain.summary import build_chip_summary
from app.fpl.cache import DiskCache
from app.optimizer.chipplan import ADVISED
from tests.fakes import FakeClaude

TEAM, LEAGUE = 5179483, 1883627
PLANS = {"team": TEAM, "league": LEAGUE, "strategy": "protect", "horizon": 4, "max_hits": 0}


@pytest.fixture(scope="module")
def chips(api: TestClient) -> s.ChipsResponse:
    r = api.get("/api/chips", params={"team": TEAM, "league": LEAGUE})
    assert r.status_code == 200, r.text
    return s.ChipsResponse.model_validate(r.json())


def test_bench_boost_and_free_hit_are_ranked_to_gw19(chips: s.ChipsResponse) -> None:
    # Nikhil used Triple Captain (GW3) and Wildcard (GW6): Bench Boost and Free Hit are left.
    assert chips.gws == list(range(11, 20))
    by_name = {c.name: c for c in chips.chips}
    assert set(by_name) == {"bboost", "freehit"}
    for c in by_name.values():
        assert c.ranked and c.stop == 19
        assert [w.gw for w in c.weeks] == list(range(11, 20))
        top = max(c.weeks, key=lambda w: (w.xpts, -w.gw))
        best = next(w for w in c.weeks if w.gw == c.best_gw)
        other = next(o for o in by_name.values() if o is not c)
        # The top week (values are shown to one decimal, so ties can hide), unless the other chip took it.
        assert best.xpts >= top.xpts - 0.05 or other.best_gw == top.gw
        assert c.lines and c.lines[-1] == "It's lost after GW19."
        assert c.play_now == (c.advised and c.best_gw == 11)
        assert c.advised == (c.name in ADVISED)
    assert by_name["bboost"].best_gw != by_name["freehit"].best_gw  # one chip per week
    # The second-half chips aren't ranked yet.
    assert {(c.name, c.start) for c in chips.later} >= {("wildcard", 20), ("bboost", 20)}


def test_week_players_are_described(chips: s.ChipsResponse) -> None:
    bb = next(c for c in chips.chips if c.name == "bboost")
    for w in bb.weeks:
        assert len(w.players) == 4
        for pid in w.players:
            player = chips.players[pid]
            assert [g.gw for g in player.gws] == chips.gws  # fixtures shown for every ranked week
        assert w.xpts == pytest.approx(sum(next(g.xpts for g in chips.players[p].gws if g.gw == w.gw) for p in w.players), abs=0.1)
    assert "No blank or double gameweeks" in chips.fixture_note


def test_plan_link_only_within_the_plans_horizon(chips: s.ChipsResponse) -> None:
    for c in chips.chips:
        assert c.plan_link is None or (c.plan_link == c.best_gw and 11 <= c.plan_link <= 15)


def test_chosen_bench_boost_week_builds_the_bench(api: TestClient) -> None:
    plain = api.get("/api/plans", params={**PLANS, "chips": False}).json()["plans"][0]
    boosted = api.get("/api/plans", params={**PLANS, "chips": False, "bboost": 13}).json()
    plan = boosted["plans"][0]
    assert boosted["bboost_gw"] == 13
    week = next(g for g in plan["gameweeks"] if g["gw"] == 13)
    assert week["chip"] == "bboost" and week["chip_xpts"] > 0
    assert all(g["chip"] is None for g in plan["gameweeks"] if g["gw"] != 13)
    assert plan["chip_xpts"] == pytest.approx(week["chip_xpts"], abs=0.01)
    # Counting the bench fully that week never makes the plan's total worse.
    assert plan["xpts"] >= plain["xpts"] - 0.01


def test_chip_choices_are_checked(api: TestClient) -> None:
    r = api.get("/api/plans", params={**PLANS, "bboost": 17})
    assert r.status_code == 400 and "isn't in this plan" in r.json()["detail"]
    r = api.get("/api/plans", params={**PLANS, "bboost": 12, "freehit": 12})
    assert r.status_code == 400 and "one chip" in r.json()["detail"]
    r = api.get("/api/plans", params={**PLANS, "tcap": 12})  # Triple Captain was used in GW3
    assert r.status_code == 400 and "don't have" in r.json()["detail"]


# ---- Claude's reason ---------------------------------------------------------------------------

@pytest.fixture
def fake_claude(tmp_path: Path) -> Iterator[FakeClaude]:
    fake = FakeClaude({"why": "placeholder", "watch_out": "placeholder"})
    set_explainer(Explainer(fake, DiskCache(tmp_path)))
    yield fake
    set_explainer(None)


def test_chip_facts_come_from_the_planner(chips: s.ChipsResponse) -> None:
    for c in chips.chips:
        summary = build_chip_summary(chips, c)
        best = next(w for w in c.weeks if w.gw == c.best_gw)
        assert summary["best_week"] == f"GW{c.best_gw}"
        assert summary["best_week_expected_points_added"] == round(best.xpts, 1)
        assert summary["verdict"] == ("guide only" if not c.advised else "play this week" if c.play_now else "hold")
        assert len(summary["weeks"]) == 9
        text = facts_text(summary)
        assert not re.search(r'"[^"]*\d[^"]*":', text)  # keys carry no numbers
        if c.name == "bboost":
            for pid in best.players:
                assert chips.players[pid].name in text


def test_chip_explain_route(api: TestClient, fake_claude: FakeClaude, chips: s.ChipsResponse) -> None:
    c = chips.chips[0]
    best = next(w for w in c.weeks if w.gw == c.best_gw)
    reason = {"why": f"GW{c.best_gw} adds {best.xpts:.1f} expected points.", "watch_out": "Fixtures can move."}
    fake_claude.replies = [reason]
    r = api.get("/api/chips/explain", params={"team": TEAM, "league": LEAGUE, "chip": c.name})
    assert r.status_code == 200
    assert r.json() == {"chip": c.name, "status": "ok", **reason}
    sent = fake_claude.calls[0]
    assert "chip planner" in sent["system"]
    assert numbers_in(reason["why"]) <= numbers_in(sent["messages"][0]["content"])


def test_chip_explain_hides_invented_numbers(api: TestClient, fake_claude: FakeClaude) -> None:
    fake_claude.replies = [{"why": "It adds 987.6 points.", "watch_out": "None."}]
    r = api.get("/api/chips/explain", params={"team": TEAM, "league": LEAGUE, "chip": "bboost"})
    assert r.json()["status"] == "unavailable"


def test_chip_explain_for_a_chip_you_dont_have(api: TestClient, fake_claude: FakeClaude) -> None:
    r = api.get("/api/chips/explain", params={"team": TEAM, "league": LEAGUE, "chip": "3xc"})
    assert r.json()["status"] == "unavailable" and not fake_claude.calls
