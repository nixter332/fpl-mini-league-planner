"""Chips in the optimizer, on Nikhil's real squad (GW11-14)."""

import time
from dataclasses import replace

import pytest

from app.model.scoring import GKP
from app.optimizer.chips import BENCH_BOOST, FREE_HIT, TRIPLE_CAPTAIN, WILDCARD, ChipWindow
from app.optimizer.inputs import build_pool
from app.optimizer.plans import make_plans, score, validate
from app.optimizer.ownership import NO_RIVALS
from app.optimizer.solver import Settings, solve
from app.model.project import project

GWS = (11, 12, 13, 14)


@pytest.fixture(scope="module")
def pool(season, manager_state):
    return build_pool(season.bootstrap, project(season, train_through=9, target_gws=GWS), manager_state, GWS)


def players(pool):
    return {p.element: p for p in pool}


def x(pool, p, g):
    return players(pool)[p].xpts.get(g, 0.0)


def with_chips(state, *windows):
    return replace(state, chips=tuple(windows))


def test_expiring_bench_boost_is_played_in_the_best_week(pool, manager_state) -> None:
    state = with_chips(manager_state, ChipWindow(BENCH_BOOST, 11, 14))  # lost after GW14: keep value 0
    sol = solve(pool, state, Settings(GWS, strategy="protect", chips=state.chips, time_limit=20))
    played = [g for g in sol.gameweeks if g.chip == BENCH_BOOST]
    assert len(played) == 1
    assert validate(sol, players(pool), state, Settings(GWS, chips=state.chips)) == []
    bench_value = lambda g: sum(x(pool, p, g.gw) for p in g.bench)
    assert bench_value(played[0]) >= max(bench_value(g) for g in sol.gameweeks) - 1.0


def test_expiring_triple_captain_goes_on_the_best_captain_week(pool, manager_state) -> None:
    state = with_chips(manager_state, ChipWindow(TRIPLE_CAPTAIN, 11, 14))
    sol = solve(pool, state, Settings(GWS, strategy="protect", chips=state.chips, time_limit=20))
    played = [g for g in sol.gameweeks if g.chip == TRIPLE_CAPTAIN]
    assert len(played) == 1
    cap_value = lambda g: x(pool, g.captain, g.gw)
    assert cap_value(played[0]) >= max(cap_value(g) for g in sol.gameweeks) - 0.5
    plain = solve(pool, state, Settings(GWS, strategy="protect", time_limit=20))
    s = Settings(GWS, chips=state.chips)
    assert score(sol, players(pool), NO_RIVALS, s)[0] == pytest.approx(score(plain, players(pool), NO_RIVALS, s)[0] + cap_value(played[0]), abs=1.0)


def test_a_chip_worth_more_later_is_kept(pool, manager_state) -> None:
    state = with_chips(manager_state, ChipWindow(BENCH_BOOST, 11, 38), ChipWindow(TRIPLE_CAPTAIN, 11, 38))
    keep = ((BENCH_BOOST, 100.0), (TRIPLE_CAPTAIN, 100.0))
    sol = solve(pool, state, Settings(GWS, strategy="protect", chips=state.chips, chip_keep=keep, time_limit=20))
    assert all(g.chip is None for g in sol.gameweeks)


def test_chips_are_off_without_permission(pool, manager_state) -> None:
    state = with_chips(manager_state, ChipWindow(BENCH_BOOST, 11, 14))
    sol = solve(pool, state, Settings(GWS, chips=state.chips, auto_chips=frozenset(), time_limit=20))
    assert all(g.chip is None for g in sol.gameweeks)


def test_wildcard_allows_many_transfers_without_hits(pool, manager_state) -> None:
    state = with_chips(manager_state, ChipWindow(WILDCARD, 11, 19))
    settings = Settings(GWS, strategy="protect", chips=state.chips, forced_chips=((11, WILDCARD),), time_limit=20)
    sol = solve(pool, state, settings)
    first = sol.first
    assert first.chip == WILDCARD and first.hits == 0
    assert len(first.transfers_in) > state.free_transfers  # more moves than free transfers
    assert sol.gameweeks[1].free_transfers == first.free_transfers  # banked transfers kept, no +1
    assert validate(sol, players(pool), state, settings) == []


def test_free_hit_squad_reverts_next_week(pool, manager_state) -> None:
    state = with_chips(manager_state, ChipWindow(FREE_HIT, 11, 19))
    settings = Settings(GWS, strategy="protect", chips=state.chips, forced_chips=((12, FREE_HIT),), time_limit=20)
    sol = solve(pool, state, settings)
    gw11, gw12, gw13 = sol.gameweeks[:3]
    assert gw12.chip == FREE_HIT and gw12.hits == 0 and gw12.bank == gw11.bank
    assert set(gw12.squad) != set(gw11.squad)  # a different one-week squad
    assert set(gw13.squad) == (set(gw11.squad) - set(gw13.transfers_out)) | set(gw13.transfers_in)
    assert validate(sol, players(pool), state, settings) == []


def test_unavailable_chip_is_refused(pool, manager_state) -> None:
    with pytest.raises(ValueError, match="Wildcard isn't available"):
        solve(pool, manager_state, Settings(GWS, chips=manager_state.chips, forced_chips=((11, WILDCARD),)))


def test_real_chips_plans_are_valid_and_fast(pool, manager_state) -> None:
    """Nikhil has Free Hit and Bench Boost left: plans with the planner free to play Bench Boost."""
    settings = Settings(GWS, strategy="balanced", chips=manager_state.chips)
    started = time.perf_counter()
    ps = make_plans(pool, manager_state, settings)
    assert time.perf_counter() - started < 6.0
    for plan in ps.plans:
        assert validate(plan.solution, players(pool), manager_state, settings) == []
        assert all(g.chip in (None, BENCH_BOOST) for g in plan.solution.gameweeks)


def test_free_hit_this_week_gives_different_plans(pool, manager_state) -> None:
    """Cuts must work in a Free Hit week too, or plans 2-3 repeat plan 1 (review finding)."""
    state = with_chips(manager_state, ChipWindow(FREE_HIT, 11, 19))
    settings = Settings(GWS, strategy="protect", chips=state.chips, forced_chips=((11, FREE_HIT),))
    ps = make_plans(pool, state, settings)
    squads = [frozenset(p.solution.first.squad) for p in ps.plans]
    assert len(squads) == len(set(squads))


def test_bench_boost_cannot_disguise_a_timed_out_plan(pool, manager_state, monkeypatch) -> None:
    """A timed-out 'keep the squad' result is dropped even when a Bench Boost is added after solving."""
    import app.optimizer.plans as plans_mod
    from app.optimizer.solver import assign_chips

    state = with_chips(manager_state, ChipWindow(BENCH_BOOST, 11, 14))
    settings = Settings(GWS, strategy="protect", chips=state.chips)
    real_solve = plans_mod.solve

    def slow_solve(pool_, state_, settings_, ownership_=None, *, cuts=(), warm_start=None, **kw):
        if len(cuts) == 2 and warm_start is not None:
            weeks = assign_chips(list(warm_start.gameweeks), players(pool), settings_)
            return replace(warm_start, gameweeks=tuple(weeks), proven_optimal=False)
        return real_solve(pool_, state_, settings_, ownership_, cuts=cuts, warm_start=warm_start, **kw)

    monkeypatch.setattr(plans_mod, "solve", slow_solve)
    ps = make_plans(pool, state, settings)
    assert len(ps.plans) == 2
