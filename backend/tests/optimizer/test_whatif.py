"""What-if: the user's own transfers, scored with the planner's rules and points."""

from dataclasses import replace

import pytest

from app.model.project import project
from app.optimizer.chips import ChipWindow
from app.optimizer.inputs import build_pool
from app.optimizer.ownership import NO_RIVALS
from app.optimizer.plans import make_plans, score
from app.optimizer.solver import Settings
from app.optimizer.whatif import Move, build_plan, week_points

GWS = (11, 12, 13, 14)


@pytest.fixture(scope="module")
def setup(season, manager_state):
    pool = build_pool(season.bootstrap, project(season, train_through=9, target_gws=GWS), manager_state, GWS)
    players = {p.element: p for p in pool}
    names = {e.id: e.web_name for e in season.bootstrap.elements}
    return players, names


def test_no_moves_is_the_planners_no_transfer_baseline(setup, manager_state) -> None:
    players, names = setup
    settings = Settings(GWS, strategy="protect")
    sol, problems = build_plan(manager_state, players, names, settings)
    assert problems == []
    ps = make_plans(list(players.values()), manager_state, settings, NO_RIVALS)
    assert score(sol, players, NO_RIVALS, settings)[0] == pytest.approx(score(ps.baseline, players, NO_RIVALS, settings)[0], abs=1e-6)


def test_replaying_plan_1_gives_the_same_points(setup, manager_state) -> None:
    """The gate: the planner's Plan 1, entered move by move, scores exactly the same."""
    players, names = setup
    settings = Settings(GWS, strategy="protect")
    plan1 = make_plans(list(players.values()), manager_state, settings, NO_RIVALS).plans[0].solution
    moves = [Move(g.gw, o, i) for g in plan1.gameweeks for o, i in zip(g.transfers_out, g.transfers_in)]
    captains = {g.gw: g.captain for g in plan1.gameweeks}
    sol, problems = build_plan(manager_state, players, names, settings, moves, captains)
    assert problems == []
    assert [set(g.squad) for g in sol.gameweeks] == [set(g.squad) for g in plan1.gameweeks]
    assert [g.hits for g in sol.gameweeks] == [g.hits for g in plan1.gameweeks]
    assert [g.bank for g in sol.gameweeks] == [g.bank for g in plan1.gameweeks]
    assert score(sol, players, NO_RIVALS, settings)[0] == pytest.approx(score(plan1, players, NO_RIVALS, settings)[0], abs=1e-6)


def _swap_candidate(players, state, *, same_position=True, affordable=True):
    owned = state.element_ids
    for p in sorted(owned):
        for c in sorted(players.values(), key=lambda c: c.element):
            if c.element in owned or (c.position == players[p].position) != same_position:
                continue
            cheap = c.buy_price <= players[p].sell_price + state.bank
            if cheap == affordable:
                return p, c.element
    raise AssertionError("no candidate")


def test_illegal_moves_are_skipped_with_a_plain_reason(setup, manager_state) -> None:
    players, names = setup
    settings = Settings(GWS)
    out, wrong_pos = _swap_candidate(players, manager_state, same_position=False)
    out2, pricey = _swap_candidate(players, manager_state, affordable=False)
    not_owned = next(p for p in players if p not in manager_state.element_ids)
    sol, problems = build_plan(manager_state, players, names, settings, [
        Move(11, out, wrong_pos), Move(11, out2, pricey), Move(11, not_owned, out), Move(20, out, wrong_pos),
    ])
    text = " | ".join(p.message for p in problems)
    assert "can only be swapped for another" in text
    assert "more than you have" in text
    assert "isn't in your squad" in text
    assert "GW20 isn't in this plan" in text
    assert set(sol.first.squad) == manager_state.element_ids  # nothing illegal was applied


def test_hits_and_free_transfers(setup, manager_state) -> None:
    players, names = setup
    state = replace(manager_state, free_transfers=1, bank=1000)  # lots of money: only hits matter here
    a_out, a_in = _swap_candidate(players, state)
    b_out, b_in = next((p, c) for p, c in [_swap_candidate(players, replace(state, players=tuple(x for x in state.players if x.element != a_out)))] if p != a_out)
    sol, problems = build_plan(state, players, names, Settings(GWS), [Move(11, a_out, a_in), Move(11, b_out, b_in)])
    assert [p.message for p in problems if "club" not in p.message] == []
    if len(sol.first.transfers_in) == 2:
        assert sol.first.hits == 1 and sol.gameweeks[1].free_transfers == 1
        assert week_points(sol.first, players) == pytest.approx(
            sum(players[p].xpts[11] for p in sol.first.starting) + players[sol.first.captain].xpts[11] - 4)


def test_captain_choice_and_chips(setup, manager_state) -> None:
    players, names = setup
    state = replace(manager_state, chips=(ChipWindow("bboost", 11, 19), ChipWindow("freehit", 11, 19)))
    sol, _ = build_plan(state, players, names, Settings(GWS))
    second = sorted(sol.first.starting, key=lambda p: -players[p].xpts[11])[1]
    bench = sol.first.bench[0]
    out, into = _swap_candidate(players, state)
    sol2, problems = build_plan(state, players, names, Settings(GWS), [Move(12, out, into)],
                                captains={11: second, 13: bench}, chips={11: "bboost", 12: "freehit", 14: "wildcard"})
    msgs = " | ".join(p.message for p in problems)
    assert sol2.first.captain == second and sol2.first.chip == "bboost"
    assert "isn't in your starting XI" in msgs  # a bench player can't be captain
    assert "don't have a Wildcard" in msgs
    assert sol2.gameweeks[1].chip == "freehit" and set(sol2.gameweeks[2].squad) == state.element_ids  # Free Hit reverts


def test_user_can_choose_the_lineup(setup, manager_state) -> None:
    """Bench a starter for a bench player of a valid formation; points follow the user's XI."""
    from app.model.scoring import GKP
    from app.optimizer.whatif import Swap

    players, names = setup
    settings = Settings(GWS)
    auto, _ = build_plan(manager_state, players, names, settings)
    gw = auto.first
    out = min((p for p in gw.starting if players[p].position == 3), key=lambda p: players[p].xpts[11])  # weakest midfielder
    sub = next(p for p in gw.bench if players[p].position == 3) if any(players[p].position == 3 for p in gw.bench) else None
    if sub is None:
        pytest.skip("no bench midfielder in this squad")
    sol, problems = build_plan(manager_state, players, names, settings, swaps=[Swap(11, out, sub)])
    assert problems == []
    assert sub in sol.first.starting and out in sol.first.bench
    assert players[sol.first.bench[0]].position == GKP  # bench keeps FPL order
    expected = week_points(gw, players) - players[out].xpts[11] + players[sub].xpts[11]
    if out != gw.captain:
        assert week_points(sol.first, players) == pytest.approx(expected, abs=1e-6)


def test_illegal_lineup_swaps_are_explained(setup, manager_state) -> None:
    from app.optimizer.whatif import Swap

    players, names = setup
    auto, _ = build_plan(manager_state, players, names, Settings(GWS))
    gw = auto.first
    keeper = next(p for p in gw.starting if players[p].position == 1)
    outfield_bench = next(p for p in gw.bench if players[p].position != 1)
    defs = [p for p in gw.starting if players[p].position == 2]
    fwd_bench = next((p for p in gw.bench if players[p].position == 4), None)
    swaps = [Swap(11, keeper, outfield_bench)]
    if len(defs) == 3 and fwd_bench:
        swaps.append(Swap(11, defs[0], fwd_bench))
    sol, problems = build_plan(manager_state, players, names, Settings(GWS), swaps=swaps)
    text = " | ".join(p.message for p in problems)
    assert "goalkeeper can only swap" in text
    assert set(sol.first.starting) == set(gw.starting)  # nothing illegal applied
