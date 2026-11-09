"""How managers actually play: transfers, hits, rolls, chips and captaincy (for tuning).

Pure functions over one manager's FPL history and picks, so they're easy to test. The script
scripts/manager_habits.py runs them over the collected sample and reports by group.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from app.fpl.models import EntryHistory, EntryPicks

TRANSFER_CHIPS = {"wildcard", "freehit"}


@dataclass(frozen=True)
class Habits:
    weeks: int  # gameweeks counted (no chip that changes transfers)
    points_per_gw: float  # net of hits, all weeks in range
    transfers_per_gw: float
    hits_per_gw: float  # -4s taken per week
    roll_share: float  # share of weeks with no transfer
    chips: dict[str, int]  # chip -> GW played (first half only)


def habits(history: EntryHistory, first_gw: int, last_gw: int) -> Habits:
    """Weekly habits over [first_gw, last_gw]. Wildcard and Free Hit weeks are left out of the
    transfer numbers (FPL reports them as 0 transfers)."""
    chip_weeks = {c.event: c.name for c in history.chips}
    rows = [r for r in history.current if first_gw <= r.event <= last_gw]
    normal = [r for r in rows if chip_weeks.get(r.event) not in TRANSFER_CHIPS]
    n = len(normal)
    return Habits(
        weeks=n,
        points_per_gw=sum(r.points - r.event_transfers_cost for r in rows) / max(1, len(rows)),
        transfers_per_gw=sum(r.event_transfers for r in normal) / max(1, n),
        hits_per_gw=sum(r.event_transfers_cost for r in normal) / 4 / max(1, n),
        roll_share=sum(1 for r in normal if r.event_transfers == 0) / max(1, n),
        chips={c.name: c.event for c in history.chips if c.event <= 19},
    )


def captain_of(picks: EntryPicks) -> int:
    return next(p.element for p in picks.picks if p.is_captain)


def top_projected(squad_xi: Iterable[int], xpts: Mapping[int, float]) -> int:
    """The starter with the highest projection (the model's captain on that XI)."""
    return max(squad_xi, key=lambda p: xpts.get(p, 0.0))
