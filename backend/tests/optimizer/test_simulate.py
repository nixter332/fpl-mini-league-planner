"""The plan backtest's scoring (FPL auto-subs) and week-to-week state."""

from app.model.scoring import DEF, FWD, GKP, MID
from app.optimizer.simulate import advance, score_week
from app.optimizer.solver import GameweekSolution, PoolPlayer
from app.optimizer.state import OwnedPlayer, SquadState

# 1 GK, 4 DEF, 4 MID, 2 FWD starting; bench: GK 12, DEF 13, MID 14, FWD 15
POS = {1: GKP, 2: DEF, 3: DEF, 4: DEF, 5: DEF, 6: MID, 7: MID, 8: MID, 9: MID, 10: FWD, 11: FWD,
       12: GKP, 13: DEF, 14: MID, 15: FWD}
XI, BENCH = list(range(1, 12)), [12, 13, 14, 15]


def week(minutes_zero=(), points=None, captain=10, vice=6):
    mins = {p: (0 if p in minutes_zero else 90) for p in POS}
    pts = points or {p: 2 for p in POS}
    return score_week(XI, BENCH, captain, vice, POS, mins, pts)


def test_everyone_plays() -> None:
    w = week(points={**{p: 2 for p in POS}, 10: 10})
    assert w.xi == tuple(XI) and w.captain == 10
    assert w.points == 2 * 10 + 10 + 10  # ten starters on 2, the captain on 10, doubled


def test_first_valid_bench_player_comes_on() -> None:
    w = week(minutes_zero={7})  # a midfielder misses out: the bench DEF (first outfield) comes on
    assert 13 in w.xi and 7 not in w.xi


def test_formation_is_kept() -> None:
    # Both forwards miss. DEF 13 can replace the first (forward 11 is still in the XI), but
    # MID 14 can't replace the second, as that would leave no forward, so FWD 15 comes on.
    w = week(minutes_zero={10, 11}, captain=6, vice=7)
    assert 13 in w.xi and 15 in w.xi and 14 not in w.xi
    assert sum(POS[p] == FWD for p in w.xi) >= 1


def test_keeper_only_replaced_by_keeper() -> None:
    w = week(minutes_zero={1})
    assert 12 in w.xi and sum(POS[p] == GKP for p in w.xi) == 1


def test_vice_gets_the_armband_if_the_captain_misses() -> None:
    w = week(minutes_zero={10}, points={**{p: 2 for p in POS}, 6: 7}, captain=10, vice=6)
    assert w.captain == 6
    assert w.points == sum(2 for p in w.xi) + 5 + 7  # vice's 7 counted twice


def test_advance_carries_squad_bank_and_free_transfers() -> None:
    state = SquadState(1, 4, tuple(OwnedPlayer(p, 50, 52) for p in POS), bank=10, free_transfers=1)
    pool = {16: PoolPlayer(16, MID, 1, 60, 60, {})}
    squad = tuple(p for p in POS if p != 14) + (16,)
    gw = GameweekSolution(5, (16,), (14,), 1, 0, 2, squad, tuple(XI), (12, 13, 16, 15), 10, 6)
    nxt = advance(state, gw, pool)
    assert nxt.element_ids == set(squad) and nxt.bank == 2 and nxt.picks_gw == 5
    assert nxt.free_transfers == 1  # used 1 of 1, +1 for the next week
    new = next(p for p in nxt.players if p.element == 16)
    assert new.purchase_price == new.sell_price == 60

    rolled = advance(state, GameweekSolution(5, (), (), 1, 0, 10, tuple(POS), tuple(XI), tuple(BENCH), 10, 6), pool)
    assert rolled.free_transfers == 2


def test_bench_boost_counts_all_fifteen() -> None:
    w = score_week(XI, BENCH, 10, 6, POS, {p: 90 for p in POS}, {p: 2 for p in POS}, chip="bboost")
    assert w.points == 15 * 2 + 2


def test_triple_captain_scores_three_times() -> None:
    pts = {**{p: 2 for p in POS}, 10: 8}
    w = score_week(XI, BENCH, 10, 6, POS, {p: 90 for p in POS}, pts, chip="3xc")
    assert w.points == 10 * 2 + 8 * 3


def test_chips_in_advance() -> None:
    from app.optimizer.chips import ChipWindow

    chips = (ChipWindow("freehit", 5, 19), ChipWindow("wildcard", 5, 19), ChipWindow("bboost", 5, 19))
    state = SquadState(1, 4, tuple(OwnedPlayer(p, 50, 52) for p in POS), bank=10, free_transfers=2, chips=chips)
    pool = {16: PoolPlayer(16, MID, 1, 60, 60, {})}
    squad = tuple(p for p in POS if p != 14) + (16,)
    fh = GameweekSolution(5, (16,), (14,), 2, 0, 10, squad, tuple(XI), (12, 13, 16, 15), 10, 6, chip="freehit")
    after_fh = advance(state, fh, pool)
    assert after_fh.element_ids == set(POS)  # the squad reverts
    assert after_fh.free_transfers == 2 and {c.name for c in after_fh.chips} == {"wildcard", "bboost"}
    wc = GameweekSolution(5, (16,), (14,), 2, 0, 2, squad, tuple(XI), (12, 13, 16, 15), 10, 6, chip="wildcard")
    after_wc = advance(state, wc, pool)
    assert after_wc.element_ids == set(squad) and after_wc.free_transfers == 2  # kept, no +1
