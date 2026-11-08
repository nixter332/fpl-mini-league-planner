"""Chips: which ones a manager has left, and in which gameweeks each can be played.

FPL (2025/26 onwards) gives every manager each chip twice: one for GW1–19 and one for
GW20–38 (bootstrap-static `chips` lists the windows). A chip not played by the end of its
window is lost. Only one chip can be played per gameweek.
"""

from collections.abc import Iterable
from dataclasses import dataclass

from app.fpl.models import ChipDef, ChipPlay

WILDCARD, FREE_HIT, BENCH_BOOST, TRIPLE_CAPTAIN = "wildcard", "freehit", "bboost", "3xc"
CHIP_LABELS = {WILDCARD: "Wildcard", FREE_HIT: "Free Hit", BENCH_BOOST: "Bench Boost", TRIPLE_CAPTAIN: "Triple Captain"}
TRANSFER_CHIPS = {WILDCARD, FREE_HIT}
AUTO_CHIPS = frozenset({BENCH_BOOST, TRIPLE_CAPTAIN})  # the planner chooses when to play these


@dataclass(frozen=True)
class ChipWindow:
    name: str
    start: int  # first GW it can still be played in
    stop: int  # last GW it can be played in (it's lost after this)

    def covers(self, gw: int) -> bool:
        return self.start <= gw <= self.stop


def chips_left(defs: Iterable[ChipDef], played: Iterable[ChipPlay], from_gw: int) -> tuple[ChipWindow, ...]:
    """Chips still available from `from_gw` (the next deadline) onwards, earliest window first."""
    played = list(played)
    out = []
    for d in sorted(defs, key=lambda d: (d.start_event, d.name)):
        used = any(p.name == d.name and d.start_event <= p.event <= d.stop_event for p in played)
        if not used and d.stop_event >= from_gw:
            out.append(ChipWindow(d.name, max(d.start_event, from_gw), d.stop_event))
    return tuple(out)


def window_for(chips: Iterable[ChipWindow], name: str, gw: int) -> ChipWindow | None:
    return next((c for c in chips if c.name == name and c.covers(gw)), None)
