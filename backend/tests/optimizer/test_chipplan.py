"""Chip planner (phase 7): week values, the play-now rule and one chip per week."""

from dataclasses import replace

import pytest

from app.model.project import project
from app.optimizer.chipplan import (
    CLOSE, ChipOutlook, ChipWeek, _one_chip_per_week, bench_boost_week, chip_outlook, decide, fixture_counts,
    free_hit_week,
)
from app.optimizer.chips import BENCH_BOOST, FREE_HIT, TRIPLE_CAPTAIN, WILDCARD, ChipWindow
from app.optimizer.inputs import build_pool
from app.optimizer.lineup import best_lineup
from app.optimizer.plans import validate
from app.optimizer.solver import Settings, solve

GWS = tuple(range(11, 20))


@pytest.fixture(scope="module")
def projection(season):
    return project(season, train_through=9, target_gws=GWS)


@pytest.fixture(scope="module")
def xpts(projection):
    out: dict[int, dict[int, float]] = {}
    for (e, g), v in projection["xpts"].items():
        out.setdefault(int(e), {})[int(g)] = float(v)
    return out


@pytest.fixture(scope="module")
def position(season):
    return {e.id: e.element_type for e in season.bootstrap.elements}


@pytest.fixture(scope="module")
def state(manager_state):
    return replace(manager_state, chips=(
        ChipWindow(BENCH_BOOST, 11, 19), ChipWindow(FREE_HIT, 11, 19), ChipWindow(TRIPLE_CAPTAIN, 11, 19),
        ChipWindow(WILDCARD, 11, 19),
    ))


@pytest.fixture(scope="module")
def outlooks(season, projection, state, position, xpts):
    pool_for = lambda g: build_pool(season.bootstrap, projection, state, (g,))
    return {o.chip: o for o in chip_outlook(state.chips, state, GWS, position, xpts, pool_for)}


def week(gw: int, x: float) -> ChipWeek:
    return ChipWeek(gw, x, ())


# ---- the decision rule ---------------------------------------------------------------------

def test_plays_now_only_when_this_week_is_the_best() -> None:
    assert decide([week(11, 9.0), week(12, 7.0)], 11) == (11, True, ())
    best, now, close = decide([week(11, 7.0), week(12, 9.0), week(13, 8.5)], 11)
    assert (best, now, close) == (12, False, (13,))


def test_ties_go_to_the_earliest_week_and_zero_is_never_advised() -> None:
    assert decide([week(11, 5.0), week(12, 5.0)], 11)[:2] == (11, True)
    assert decide([week(11, 0.0), week(12, 0.0)], 11) == (None, False, ())
    assert decide([], 11) == (None, False, ())


def test_two_chips_never_share_a_week() -> None:
    win = lambda n: ChipWindow(n, 11, 19)
    bb = ChipOutlook(BENCH_BOOST, win(BENCH_BOOST), (week(11, 10.0), week(12, 9.5)), 11, True)
    fh = ChipOutlook(FREE_HIT, win(FREE_HIT), (week(11, 8.0), week(12, 3.0)), 11, True)
    out = {o.chip: o for o in _one_chip_per_week([bb, fh], 11)}
    # Moving the Bench Boost costs 0.5; moving the Free Hit would cost 5. The Bench Boost moves.
    assert out[FREE_HIT].best_gw == 11 and out[FREE_HIT].play_now
    assert out[BENCH_BOOST].best_gw == 12 and not out[BENCH_BOOST].play_now


def test_blank_and_double_gameweeks_are_found() -> None:
    fixtures = [(11, 1, 2), (11, 3, 4), (11, 1, 3), (12, 1, 2)]
    counts = fixture_counts(fixtures, [1, 2, 3, 4], [11, 12])
    assert counts[11] == ([], [1, 3])  # clubs 1 and 3 play twice
    assert counts[12] == ([3, 4], [])


# ---- on Nikhil's real squad (GW11-19) --------------------------------------------------------

def test_every_open_chip_gets_an_outlook(outlooks) -> None:
    assert set(outlooks) == {BENCH_BOOST, FREE_HIT, TRIPLE_CAPTAIN, WILDCARD}
    assert outlooks[WILDCARD].weeks == () and outlooks[WILDCARD].best_gw is None  # never ranked
    for chip in (BENCH_BOOST, FREE_HIT, TRIPLE_CAPTAIN):
        assert [w.gw for w in outlooks[chip].weeks] == list(GWS)


def test_bench_boost_week_is_the_bench_of_the_best_lineup(state, position, xpts) -> None:
    x = {p: by.get(13, 0.0) for p, by in xpts.items()}
    value, bench = bench_boost_week(state.element_ids, position, x)
    lineup = best_lineup(state.element_ids, position, x)
    assert bench == lineup.bench and len(bench) == 4
    assert value == pytest.approx(sum(x[p] for p in bench))


def test_triple_captain_week_is_the_captain_again(outlooks, state, position, xpts) -> None:
    for w in outlooks[TRIPLE_CAPTAIN].weeks:
        x = {p: by.get(w.gw, 0.0) for p, by in xpts.items()}
        assert w.players == (best_lineup(state.element_ids, position, x).captain,)
        assert w.xpts == pytest.approx(x[w.players[0]], abs=0.01)


def test_best_week_is_the_highest_value_unless_moved_for_another_chip(outlooks) -> None:
    taken = {o.best_gw for o in outlooks.values() if o.best_gw is not None}
    assert len(taken) == len([o for o in outlooks.values() if o.best_gw is not None])  # one chip per week
    for o in outlooks.values():
        if o.best_gw is None:
            continue
        assert o.play_now == (o.best_gw == GWS[0])
        assert all(o.best.xpts - o.weeks[[w.gw for w in o.weeks].index(g)].xpts <= CLOSE for g in o.close)


def test_free_hit_squad_is_legal_and_affordable(season, projection, state) -> None:
    pool = build_pool(season.bootstrap, projection, state, (14,))
    value, ins, squad = free_hit_week(pool, state, 14)
    assert value >= 0 and len(squad) == 15
    assert set(ins) == set(squad) - state.element_ids
    sol = solve(pool, state, Settings((14,), strategy="protect", chips=state.chips, auto_chips=frozenset(),
                                      forced_chips=((14, FREE_HIT),)))
    assert validate(sol, {p.element: p for p in pool}, state, Settings((14,), chips=state.chips)) == []


def test_the_buy_discount_lowers_a_free_hits_value(season, projection, state) -> None:
    pool = build_pool(season.bootstrap, projection, state, (14,))
    raw = free_hit_week(pool, state, 14, discount=0.0)[0]
    discounted = free_hit_week(pool, state, 14, discount=0.25)[0]
    assert raw > 0 and discounted < raw


def test_chips_outside_the_lookahead_or_window_are_left_out(state, position, xpts) -> None:
    later = replace(state, chips=(ChipWindow(BENCH_BOOST, 20, 38),))
    assert chip_outlook(later.chips, later, GWS, position, xpts) == []
    # Without a Free Hit pool the Free Hit is listed but not ranked.
    only_fh = replace(state, chips=(ChipWindow(FREE_HIT, 11, 19),))
    [o] = chip_outlook(only_fh.chips, only_fh, GWS, position, xpts)
    assert o.chip == FREE_HIT and o.best_gw is None
