"""Plan facts and the /api/explain route, on real plans from the saved fixtures."""

import json
import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api import schemas as s
from app.api.main import get_service, set_explainer
from app.explain.check import check
from app.explain.explainer import Explainer, facts_text
from app.explain.summary import build_summary
from app.fpl.cache import DiskCache
from tests.fakes import FakeClaude

TEAM, LEAGUE = 5179483, 1883627
PARAMS = {"team": TEAM, "league": LEAGUE, "strategy": "balanced", "horizon": 4, "max_hits": 1}


@pytest.fixture(scope="module")
def plans(api: TestClient) -> s.PlansResponse:
    r = api.get("/api/plans", params=PARAMS)
    assert r.status_code == 200
    return s.PlansResponse.model_validate(r.json())


@pytest.fixture
def fake_claude(tmp_path: Path) -> Iterator[FakeClaude]:
    fake = FakeClaude({"why": "placeholder", "watch_out": "placeholder"})
    set_explainer(Explainer(fake, DiskCache(tmp_path)))
    yield fake
    set_explainer(None)


def test_facts_cover_the_plan(plans: s.PlansResponse) -> None:
    for plan in plans.plans:
        summary = build_summary(plans, plan)
        text = facts_text(summary)
        assert summary["plan"]["expected_points_gain_vs_no_transfers"] == round(plan.xpts_gain, 1)
        assert summary["plan"]["recommended"] == (plan.rank == 1)
        assert [o["recommended"] for o in summary["other_plans"]].count(True) == (0 if plan.rank == 1 else 1)
        assert "(H)" not in text and "(A)" not in text  # "at home" / "away" reads better
        assert plans.players[plan.gameweeks[0].captain].name in text
        for gw in plan.gameweeks:
            for m in gw.moves:
                assert plans.players[m.player_in].name in text and plans.players[m.player_out].name in text
        assert len(summary["other_plans"]) == len(plans.plans) - 1
        assert "league" in summary and summary["league"]["rivals_compared"] == plans.standing.n_rivals


def test_fact_keys_have_no_digits(plans: s.PlansResponse) -> None:
    """Every number in the facts counts as allowed, so keys mustn't smuggle any in."""
    def keys(x):
        if isinstance(x, dict):
            for k, v in x.items():
                yield k
                yield from keys(v)
        elif isinstance(x, list):
            for v in x:
                yield from keys(v)

    for plan in plans.plans:
        assert not [k for k in keys(build_summary(plans, plan)) if re.search(r"\d", k)]


def test_facts_name_no_rival_managers(plans: s.PlansResponse) -> None:
    text = facts_text(build_summary(plans, plans.plans[0]))
    h = plans.plans[0].head_to_head
    if h:
        assert h.opponent_name not in text and h.opponent_entry_name not in text


def test_a_faithful_reason_passes_and_a_made_up_one_fails(plans: s.PlansResponse) -> None:
    plan = next(p for p in plans.plans if not p.is_roll)
    summary = build_summary(plans, plan)
    text = facts_text(summary)
    move = summary["plan"]["transfers"][0]
    known = get_service().known_names()
    why = (
        f"{move['in']['name']} gives you {summary['plan']['expected_points_gain_vs_no_transfers']} more expected points "
        f"than keeping {move['out']['name']} over {summary['gameweeks_planned']}."
    )
    assert check(why, "Rotation could cost you.", text, known) == []
    absent = sorted(known - {n for n in known if n in text} - {"Salah"})  # any player not in this plan
    fake = next(n for n in absent if len(n) > 4 and n[0].isupper())
    assert check(f"Bring in {fake} instead.", "None.", text, known)
    assert check("You gain 123.4 points.", "None.", text, known)


def test_explain_is_off_without_a_key(api: TestClient) -> None:
    set_explainer(Explainer.from_env())  # conftest blanks the key
    try:
        r = api.get("/api/explain", params={**PARAMS, "rank": 1})
        assert r.status_code == 200 and r.json() == {"rank": 1, "status": "off", "why": None, "watch_out": None}
    finally:
        set_explainer(None)


def test_explain_returns_a_checked_reason(api: TestClient, plans: s.PlansResponse, fake_claude: FakeClaude) -> None:
    plan = plans.plans[0]
    summary = build_summary(plans, plan)
    captain = summary["plan"]["captain_this_gameweek"]
    reason = {"why": f"{captain['name']} is your captain in {summary['this_gameweek']}.", "watch_out": "Your bench is thin."}
    fake_claude.replies = [reason]
    r = api.get("/api/explain", params={**PARAMS, "rank": plan.rank})
    assert r.status_code == 200
    assert r.json() == {"rank": plan.rank, "status": "ok", **reason}
    sent = fake_claude.calls[0]["messages"][0]["content"]
    assert json.dumps(captain["name"], ensure_ascii=False) in sent


def test_explain_hides_a_reason_that_fails_the_check(api: TestClient, fake_claude: FakeClaude) -> None:
    fake_claude.replies = [{"why": "You gain 987.6 points.", "watch_out": "None."}]
    r = api.get("/api/explain", params={**PARAMS, "rank": 1})
    assert r.json()["status"] == "unavailable" and r.json()["why"] is None
    assert len(fake_claude.calls) == 2  # one retry


def test_explain_validates_rank(api: TestClient, fake_claude: FakeClaude) -> None:
    assert api.get("/api/explain", params={**PARAMS, "rank": 0}).status_code == 422
    assert api.get("/api/explain", params={**PARAMS, "rank": 4}).status_code == 422


def test_captain_facts_show_the_trade_off(plans: s.PlansResponse) -> None:
    """When the captain isn't the top projected starter (a differential captain), the facts say
    who is, and how many rivals captained each, so the reason can explain the choice."""
    for plan in plans.plans:
        facts = build_summary(plans, plan)["plan"]
        first = plan.gameweeks[0]
        x = lambda p: next(g.xpts for g in plans.players[p].gws if g.gw == first.gw)
        top = max(plan.after.starting, key=x)
        assert "rivals_who_captained_him_last_week" in facts["captain_this_gameweek"]
        if x(top) > x(first.captain):
            assert facts["highest_projected_player_in_your_team"]["name"] == plans.players[top].name
        else:
            assert "highest_projected_player_in_your_team" not in facts


def test_facts_include_saved_free_transfers(plans: s.PlansResponse) -> None:
    """The ranking values free transfers left at the end, so Claude must know them."""
    from app.explain.summary import free_transfers_after

    for plan in plans.plans:
        facts = build_summary(plans, plan)
        text = facts["plan"]["free_transfers_after_the_whole_plan"]
        assert text == f"{free_transfers_after(plan)} going into GW{plan.gameweeks[-1].gw + 1}"
        assert 1 <= free_transfers_after(plan) <= 5
        assert all("free_transfers_after_the_whole_plan" in o for o in facts["other_plans"])


def test_facts_describe_chips(api: TestClient) -> None:
    body = api.get("/api/plans", params={**PARAMS, "horizon": 3, "freehit": 11}).json()
    resp = s.PlansResponse.model_validate(body)
    facts = build_summary(resp, resp.plans[0])
    played = facts["plan"]["chips_played"]
    fh = next(c for c in played if c["chip"] == "Free Hit")
    assert fh["gameweek"] == 11 and fh["chosen_by"] == "you" and "one-week" in fh["meaning"]
    assert any(t.get("free_hit_one_week_only") for t in facts["plan"]["transfers"])
    assert any("Bench Boost" in c for c in facts["chips_left"])
    # "GW11" etc. in labels: the numbers are all in the facts, so the trust check allows them
    text = facts_text(facts)
    assert check("Your Free Hit in GW11 brings in a one-week squad.", "None.", text, get_service().known_names()) == []
