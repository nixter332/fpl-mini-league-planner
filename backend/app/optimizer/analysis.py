"""Weak spots in a squad and the best single replacements (phase 8, docs/plans/phase-8.md).

A swap's value is what it does to the whole team: each week's best XI and captain with the new
player in, minus without, plus a little for the bench (the solver's bench weight, 0 for keepers),
summed over the horizon. So an injured regular, who'd currently sit on the bench, shows up as a
weak spot because replacing him lifts the XI. Only swaps the manager could actually make are
considered: same position, affordable from his selling price plus the bank, at most 3 per club.
The best swap's gain sets the colour; replacements are ranked by the chosen strategy, weighing
rivals' ownership the way the planner does.
"""

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from app.model.scoring import GKP
from app.optimizer.lineup import best_lineup
from app.optimizer.ownership import NO_RIVALS, LeagueOwnership
from app.optimizer.solver import MAX_PER_CLUB, PoolPlayer
from app.optimizer.state import SquadState

RED_GAP = 6.0  # projected team points over the horizon
AMBER_GAP = 3.0
UNAVAILABLE = 0.5  # chance of playing next week below this, for a player who'd otherwise start: red
BENCH_WEIGHT = 0.1
SHORTLIST = 15  # candidates per player scored exactly
TOP_N = 3


@dataclass(frozen=True)
class Replacement:
    element: int
    gain: float  # projected team points over the horizon, vs keeping the player
    weighted_gain: float  # the same, weighted by the strategy (what the ranking uses)


@dataclass(frozen=True)
class Spot:
    element: int
    level: str  # "red", "amber" or "ok"
    reason: str | None  # "unavailable", "upgrade" or None
    gap: float  # gain of the best affordable swap (0 if none)
    replacements: tuple[Replacement, ...]


class _Team:
    """Weekly value of a squad: best XI + captain, plus the weighted bench."""

    def __init__(self, players: Mapping[int, PoolPlayer], gws: Sequence[int], ownership: LeagueOwnership, weight: float):
        self.players, self.gws, self.own, self.w = players, gws, ownership, weight

    def value(self, squad: frozenset[int]) -> tuple[float, float]:
        """(points, strategy-weighted points) over the horizon."""
        pts = weighted = 0.0
        position = {p: self.players[p].position for p in squad}
        for g in self.gws:
            x = {p: self.players[p].xpts.get(g, 0.0) for p in squad}
            lu = best_lineup(squad, position, x)
            start_w = lambda p: 1 - self.w * min(self.own.start_share(p), 1.0)
            cap_w = 1 - self.w * min(self.own.captain_share(lu.captain), 1.0)
            pts += lu.xpts
            weighted += sum(x[p] * start_w(p) for p in lu.starting) + x[lu.captain] * cap_w
            for p in lu.bench:
                if position[p] != GKP:
                    pts += BENCH_WEIGHT * x[p]
                    weighted += BENCH_WEIGHT * x[p] * start_w(p)
        return pts, weighted


def analyse(
    state: SquadState,
    players: Mapping[int, PoolPlayer],
    buyable: set[int],
    gws: Sequence[int],
    availability: Mapping[int, float],
    ownership: LeagueOwnership = NO_RIVALS,
    weight: float = 0.0,
) -> list[Spot]:
    """One Spot per squad player. `availability` is each player's chance of playing next week."""
    team = _Team(players, gws, ownership, weight)
    squad = frozenset(state.element_ids)
    base_pts, base_weighted = team.value(squad)
    clubs = Counter(players[p].team for p in squad)
    sell = {p.element: p.sell_price for p in state.players}
    first_xi = set(best_lineup(squad, {p: players[p].position for p in squad}, {p: players[p].xpts.get(gws[0], 0.0) for p in squad}).starting)

    spots = []
    for p in sorted(squad):
        me = players[p]
        budget = sell.get(p, me.sell_price) + state.bank
        legal = [
            c for c in buyable
            if c not in squad and players[c].position == me.position and players[c].buy_price <= budget
            and (players[c].team == me.team or clubs[players[c].team] + 1 <= MAX_PER_CLUB)
        ]
        # Rough shortlist (as if both start every week), then the exact team value for those.
        rough = lambda c: sum(players[c].xpts.get(g, 0.0) for g in gws)
        shortlist = sorted(legal, key=lambda c: (-rough(c), c))[:SHORTLIST]
        options = []
        for c in shortlist:
            pts, weighted = team.value((squad - {p}) | {c})
            options.append(Replacement(c, round(pts - base_pts, 2), round(weighted - base_weighted, 2)))
        options.sort(key=lambda r: (-r.weighted_gain, -r.gain, r.element))
        top = tuple(r for r in options[:TOP_N] if r.gain > 0 or r.weighted_gain > 0)
        gap = max((r.gain for r in options), default=0.0)
        # "Unavailable" only matters for someone who'd play if fit: he's in this week's XI, or a fit
        # replacement in his place would lift the team by the amber margin or more.
        unavailable = availability.get(p, 1.0) < UNAVAILABLE and (p in first_xi or gap >= AMBER_GAP)
        if unavailable or gap >= RED_GAP:
            level, reason = "red", "unavailable" if unavailable else "upgrade"
        elif gap >= AMBER_GAP:
            level, reason = "amber", "upgrade"
        else:
            level, reason = "ok", None
        spots.append(Spot(p, level, reason, round(max(gap, 0.0), 2), top))
    return spots
