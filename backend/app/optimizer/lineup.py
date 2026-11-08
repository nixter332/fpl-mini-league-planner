"""Best starting XI and captain for a fixed 15-man squad, in one gameweek.

Greedy is exact here: take the best GK, the formation minimums (3 DEF, 2 MID, 1 FWD), then
the best remaining outfielders. A 5/5/3 squad can never break the maximums. Used for the
Team screen and for projecting rivals' squads, where a full MILP per rival would be too slow.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from app.model.scoring import DEF, FWD, GKP, MID

XI_MINIMUMS = {DEF: 3, MID: 2, FWD: 1}


@dataclass(frozen=True)
class Lineup:
    starting: tuple[int, ...]
    bench: tuple[int, ...]  # backup GK first, then outfield by xPts
    captain: int
    vice: int
    xpts: float  # XI + captain bonus


def best_lineup(squad: Iterable[int], position: Mapping[int, int], xpts: Mapping[int, float]) -> Lineup:
    players = list(squad)
    by_xpts = sorted(players, key=lambda p: -xpts.get(p, 0.0))
    keepers = [p for p in by_xpts if position[p] == GKP]
    outfield = [p for p in by_xpts if position[p] != GKP]

    starting = keepers[:1]
    for pos, n in XI_MINIMUMS.items():
        starting += [p for p in outfield if position[p] == pos][:n]
    starting += [p for p in outfield if p not in starting][: 11 - len(starting)]

    order = sorted(starting, key=lambda p: -xpts.get(p, 0.0))
    captain, vice = order[0], order[1]
    bench = keepers[1:] + [p for p in outfield if p not in starting]
    total = sum(xpts.get(p, 0.0) for p in starting) + xpts.get(captain, 0.0)
    return Lineup(tuple(starting), tuple(bench), captain, vice, total)


def picks_projection(
    picks: Iterable[tuple[int, int]], position: Mapping[int, int], xpts: Mapping[int, float]
) -> float:
    """A rival's projected points for a GW: their best lineup from last week's 15.

    `picks` is (element, multiplier) pairs; a triple captain or bench boost from last week
    isn't assumed to repeat.
    """
    return best_lineup([e for e, _ in picks], position, xpts).xpts
