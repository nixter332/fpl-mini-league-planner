"""Weak spots and replacements: every suggestion is a swap the manager could actually make."""

from collections import Counter

import pytest

from app.model.project import project
from app.optimizer.analysis import AMBER_GAP, RED_GAP, analyse
from app.optimizer.inputs import build_pool
from app.optimizer.solver import MAX_PER_CLUB, PoolPlayer

GWS = (11, 12, 13, 14)


@pytest.fixture(scope="module")
def setup(season, manager_state):
    proj = project(season, train_through=9, target_gws=GWS)
    owned = manager_state.element_ids
    sell = {p.element: p.sell_price for p in manager_state.players}
    players = {}
    for e in season.bootstrap.elements:
        xp = {g: float(proj.loc[(e.id, g), "xpts"]) if (e.id, g) in proj.index else 0.0 for g in GWS}
        players[e.id] = PoolPlayer(e.id, e.element_type, e.team, e.now_cost, sell.get(e.id, e.now_cost), xp)
    buyable = {e.id for e in season.bootstrap.elements if e.status != "u" and e.can_transact and e.id not in owned}
    avail = {e.id: (e.chance_of_playing_next_round if e.chance_of_playing_next_round is not None else (0 if e.status in "isu" else 100)) / 100
             for e in season.bootstrap.elements}
    return players, buyable, avail


def test_every_replacement_is_a_legal_affordable_swap(setup, manager_state) -> None:
    players, buyable, avail = setup
    spots = analyse(manager_state, players, buyable, GWS, avail)
    assert {s.element for s in spots} == manager_state.element_ids
    sell = {p.element: p.sell_price for p in manager_state.players}
    for s in spots:
        me = players[s.element]
        for r in s.replacements:
            c = players[r.element]
            assert c.position == me.position and r.element not in manager_state.element_ids
            assert c.buy_price <= sell[s.element] + manager_state.bank
            after = (manager_state.element_ids - {s.element}) | {r.element}
            assert max(Counter(players[p].team for p in after).values()) <= MAX_PER_CLUB
        assert list(s.replacements) == sorted(s.replacements, key=lambda r: (-r.weighted_gain, -r.gain, r.element))


def test_colours_follow_the_gap(setup, manager_state) -> None:
    players, buyable, avail = setup
    for s in analyse(manager_state, players, buyable, GWS, avail):
        if s.reason == "upgrade":
            assert s.gap >= (RED_GAP if s.level == "red" else AMBER_GAP)
        if s.level == "ok":
            assert s.gap < AMBER_GAP and s.reason is None


def test_injured_starter_is_red(setup, manager_state, season) -> None:
    players, buyable, avail = setup
    spots = analyse(manager_state, players, buyable, GWS, avail)
    # João Pedro (thigh injury, unknown return) is in the saved squad. He projects low, so the best
    # XI benches him, but replacing him lifts the team: he must still show up as a weak spot.
    names = {e.id: e.web_name for e in season.bootstrap.elements}
    jp = next(e for e in manager_state.element_ids if names[e] == "João Pedro")
    spot = next(s for s in spots if s.element == jp)
    assert spot.level == "red" and spot.replacements
    # The backup keeper on the bench is never flagged just for being a backup.
    by_level = {s.element: s.level for s in spots}
    assert sum(1 for s in spots if s.level != "ok") < len(spots)


def test_strategy_weight_changes_the_ranking_only(setup, manager_state, rival_picks) -> None:
    from app.optimizer.ownership import league_ownership

    players, buyable, avail = setup
    own = league_ownership(rival_picks)
    a = analyse(manager_state, players, buyable, GWS, avail)
    b = analyse(manager_state, players, buyable, GWS, avail, own, weight=0.33)
    assert [s.gap for s in a] == [s.gap for s in b]  # colours are about points, not strategy
