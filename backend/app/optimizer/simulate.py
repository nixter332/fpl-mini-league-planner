"""Replaying plans against what really happened (the plan backtest).

Each simulated week: the planner picks transfers, an XI and a captain from the squad it has;
we score that with the real points, applying FPL's automatic substitutions, then carry the
squad, bank and free transfers into the next week.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from app.model.scoring import DEF, FWD, GKP, MID
from app.optimizer.chips import BENCH_BOOST, FREE_HIT, TRANSFER_CHIPS, TRIPLE_CAPTAIN
from app.optimizer.solver import GameweekSolution, PoolPlayer
from app.optimizer.state import MAX_FREE_TRANSFERS, OwnedPlayer, SquadState

XI_MIN = {GKP: 1, DEF: 3, MID: 2, FWD: 1}


@dataclass(frozen=True)
class ScoredWeek:
    points: int  # XI after auto-subs, captain doubled, before hits
    xi: tuple[int, ...]  # the XI that actually scored (after auto-subs)
    captain: int | None  # whoever got the armband (the vice if the captain didn't play)


def _formation_ok(xi: Sequence[int], position: Mapping[int, int]) -> bool:
    counts = {pos: 0 for pos in XI_MIN}
    for p in xi:
        counts[position[p]] += 1
    return counts[GKP] == 1 and all(counts[pos] >= n for pos, n in XI_MIN.items())


def score_week(
    starting: Sequence[int],
    bench: Sequence[int],
    captain: int,
    vice: int,
    position: Mapping[int, int],
    minutes: Mapping[int, int],
    points: Mapping[int, int],
    chip: str | None = None,
) -> ScoredWeek:
    """FPL's rules: a starter who didn't play is replaced by the first bench player (in order)
    who did, if the formation stays valid; a keeper can only be replaced by the bench keeper.
    If the captain didn't play, the vice is doubled instead. Bench Boost: all 15 score (no
    auto-subs needed). Triple Captain: the armband scores three times."""
    if chip == BENCH_BOOST:
        xi = list(starting) + list(bench)
        armband = captain if minutes.get(captain, 0) > 0 else vice if minutes.get(vice, 0) > 0 else None
        total = sum(points.get(p, 0) for p in xi) + (points.get(armband, 0) if armband else 0)
        return ScoredWeek(total, tuple(xi), armband)
    xi = list(starting)
    used: set[int] = set()
    for i, p in enumerate(list(xi)):
        if minutes.get(p, 0) > 0:
            continue
        for b in bench:
            if b in used or minutes.get(b, 0) == 0:
                continue
            if (position[b] == GKP) != (position[p] == GKP):
                continue
            trial = xi[:i] + [b] + xi[i + 1:]
            if _formation_ok(trial, position):
                xi, used = trial, used | {b}
                break
    armband = captain if minutes.get(captain, 0) > 0 else vice if minutes.get(vice, 0) > 0 and vice in xi else None
    extra = 2 if chip == TRIPLE_CAPTAIN else 1
    total = sum(points.get(p, 0) for p in xi) + (extra * points.get(armband, 0) if armband else 0)
    return ScoredWeek(total, tuple(xi), armband)


def advance(state: SquadState, gw: GameweekSolution, pool: Mapping[int, PoolPlayer], max_free: int = MAX_FREE_TRANSFERS) -> SquadState:
    """The squad after this week's transfers, ready for the next deadline. Players bought
    in the simulation sell for what was paid (prices are held at today's values). A played
    chip is used up; after a Wildcard or Free Hit the banked free transfers are kept (no +1),
    and after a Free Hit the squad reverts."""
    chips = tuple(c for c in state.chips if not (c.name == gw.chip and c.covers(gw.gw)))
    if gw.chip == FREE_HIT:
        return SquadState(state.entry_id, gw.gw, state.players, state.bank, state.free_transfers, chips)
    owned = {p.element: p for p in state.players}
    players = []
    for e in gw.squad:
        if e in owned:
            players.append(owned[e])
        else:
            price = pool[e].buy_price
            players.append(OwnedPlayer(e, price, price))
    free_used = len(gw.transfers_in) - gw.hits
    ft = state.free_transfers if gw.chip in TRANSFER_CHIPS else min(state.free_transfers - free_used + 1, max_free)
    return SquadState(
        entry_id=state.entry_id,
        picks_gw=gw.gw,
        players=tuple(players),
        bank=gw.bank,
        free_transfers=ft,
        chips=chips,
    )
