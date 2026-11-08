"""League effective ownership from rivals' latest picks.

Split into two parts, each a fraction of rivals in [0, 1]:
- start: rivals who have the player in their scoring XI (multiplier >= 1),
- captain: rivals who captain him (triple captain counts once here; it's still capped at 1).

The classic EO (start + captain, so up to ~2) is kept for display. The optimizer weights a
player's starting points by (1 - w * start) and his captain bonus by (1 - w * captain), so a
weight is never negative and the solver never prefers dropping a high scorer for nothing.
"""

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field

from app.fpl.models import EntryPicks


@dataclass(frozen=True)
class LeagueOwnership:
    n_rivals: int
    start: dict[int, float] = field(default_factory=dict)
    captain: dict[int, float] = field(default_factory=dict)
    eo: dict[int, float] = field(default_factory=dict)  # classic: sum of multipliers / rivals

    def start_share(self, element: int) -> float:
        return self.start.get(element, 0.0)

    def captain_share(self, element: int) -> float:
        return self.captain.get(element, 0.0)


NO_RIVALS = LeagueOwnership(n_rivals=0)


def league_ownership(rival_picks: Iterable[EntryPicks]) -> LeagueOwnership:
    picks = list(rival_picks)
    if not picks:
        return NO_RIVALS
    starts: Counter[int] = Counter()
    captains: Counter[int] = Counter()
    multipliers: Counter[int] = Counter()
    for team in picks:
        for p in team.picks:
            multipliers[p.element] += p.multiplier
            if p.multiplier >= 1:
                starts[p.element] += 1
            if p.multiplier >= 2:
                captains[p.element] += 1
    n = len(picks)
    return LeagueOwnership(
        n_rivals=n,
        start={e: c / n for e, c in starts.items()},
        captain={e: c / n for e, c in captains.items()},
        eo={e: m / n for e, m in multipliers.items()},
    )
