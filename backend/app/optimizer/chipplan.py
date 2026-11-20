"""Chip planner (phase 7): what each chip a manager has left is projected to add in every
remaining week of its window, and whether to play it this week or hold it.

The planner decides; nothing here is written by an LLM. For each week:
- Bench Boost: the projected points of the bench (all four) in the best lineup of the squad.
- Triple Captain: the captain's projected points again.
- Free Hit: a one-week solve for the best squad the manager can afford (squad selling value plus
  bank), minus the best lineup of their own squad. FREE_HIT_BUY_DISCOUNT can shrink the
  projections of players it brings in; it's 0 because the backtest couldn't calibrate it (see
  docs/chip-planner.md: without past injury news, Free Hit squads scored far below projection).
- Wildcard: not ranked. Its value lasts for weeks after it's played, and our Wildcard advice
  lost 18 points on 412 managers, so the page only says when it expires.

Every week is scored with the squad the manager has now. Transfers before then change the
numbers, so the page is recomputed each week.

The decision rule ("play now if this week is the best remaining week") is the one tested in
`scripts/backtest_chips.py`; results and the gate are in docs/chip-planner.md.
"""

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace

from app.optimizer.chips import BENCH_BOOST, FREE_HIT, TRIPLE_CAPTAIN, WILDCARD, ChipWindow
from app.optimizer.lineup import best_lineup
from app.optimizer.solver import PoolPlayer, Settings, solve
from app.optimizer.state import SquadState

# How many weeks ahead are ranked. Covers GW11-19 from GW11; weeks further out are too uncertain.
LOOKAHEAD = 9
# Share taken off the projections of players a Free Hit brings in (see the module docstring).
FREE_HIT_BUY_DISCOUNT = 0.0
# Weeks whose values are this close count as a tie: small differences are noise, not advice.
CLOSE = 1.0
RANKED = (BENCH_BOOST, TRIPLE_CAPTAIN, FREE_HIT)
# Chips whose "play now / hold" rule passed the backtest gate (docs/chip-planner.md). For the
# others the page shows the weeks' values without telling the manager when to play.
# None yet (20 Nov 2026, GW5-10 on 416 managers): Bench Boost timing did no better than a random
# week, Free Hit timing did worse, and Triple Captain's edge came from a single week (GW7).
ADVISED: frozenset[str] = frozenset()


@dataclass(frozen=True)
class ChipWeek:
    gw: int
    xpts: float  # what the chip is projected to add that week
    players: tuple[int, ...]  # Bench Boost: the bench; Triple Captain: the captain; Free Hit: players in


@dataclass(frozen=True)
class ChipOutlook:
    chip: str
    window: ChipWindow
    weeks: tuple[ChipWeek, ...]  # every ranked week, in gameweek order (empty for a Wildcard)
    best_gw: int | None  # the planner's week (None: not ranked)
    play_now: bool  # the best week is this week
    close: tuple[int, ...] = ()  # other weeks within CLOSE of the best

    @property
    def best(self) -> ChipWeek | None:
        return next((w for w in self.weeks if w.gw == self.best_gw), None)

    def ranked(self) -> list[ChipWeek]:
        return sorted(self.weeks, key=lambda w: (-w.xpts, w.gw))


def bench_boost_week(squad: Iterable[int], position: Mapping[int, int], xpts: Mapping[int, float]) -> tuple[float, tuple[int, ...]]:
    lineup = best_lineup(squad, position, xpts)
    return sum(xpts.get(p, 0.0) for p in lineup.bench), lineup.bench


def triple_captain_week(squad: Iterable[int], position: Mapping[int, int], xpts: Mapping[int, float]) -> tuple[float, tuple[int, ...]]:
    lineup = best_lineup(squad, position, xpts)
    return xpts.get(lineup.captain, 0.0), (lineup.captain,)


def free_hit_week(
    pool: Sequence[PoolPlayer], state: SquadState, gw: int, *, discount: float = FREE_HIT_BUY_DISCOUNT,
    time_limit: float = 5.0,
) -> tuple[float, tuple[int, ...], tuple[int, ...]]:
    """(xPts the Free Hit adds in `gw`, players it brings in, the whole one-week squad). `pool`
    must cover `gw` and contain the whole squad; `state.chips` must include a Free Hit window
    covering `gw`."""
    owned = state.element_ids
    pool = [p if p.element in owned else replace(p, xpts={g: x * (1 - discount) for g, x in p.xpts.items()}) for p in pool]
    position = {p.element: p.position for p in pool}
    xpts = {p.element: p.xpts.get(gw, 0.0) for p in pool}
    mine = best_lineup(owned, position, xpts).xpts
    settings = Settings(
        (gw,), strategy="protect", chips=state.chips, auto_chips=frozenset(), forced_chips=((gw, FREE_HIT),),
        time_limit=time_limit,
    )
    sol = solve(pool, state, settings)
    if sol is None:
        return 0.0, (), tuple(sorted(owned))
    week = sol.first
    theirs = sum(xpts[p] for p in week.starting) + xpts[week.captain]
    return max(0.0, theirs - mine), tuple(sorted(set(week.squad) - owned)), tuple(sorted(week.squad))


def decide(weeks: Sequence[ChipWeek], first_gw: int) -> tuple[int | None, bool, tuple[int, ...]]:
    """(best week, play it now, other weeks within CLOSE of it). Ties go to the earliest week:
    it's the surer projection, and playing it frees the week for nothing else."""
    if not weeks:
        return None, False, ()
    best = max(weeks, key=lambda w: (round(w.xpts, 6), -w.gw))
    if best.xpts <= 0:
        return None, False, ()
    close = tuple(w.gw for w in weeks if w.gw != best.gw and best.xpts - w.xpts <= CLOSE)
    return best.gw, best.gw == first_gw, close


def chip_outlook(
    chips: Iterable[ChipWindow],
    state: SquadState,
    gws: Sequence[int],
    position: Mapping[int, int],
    xpts: Mapping[int, Mapping[int, float]],  # element -> gw -> xPts
    free_hit_pool: Callable[[int], Sequence[PoolPlayer]] | None = None,
    *,
    discount: float = FREE_HIT_BUY_DISCOUNT,
) -> list[ChipOutlook]:
    """An outlook for every chip window that's open in `gws` (the next actionable GW first).

    `free_hit_pool(gw)` returns the player pool for a one-week Free Hit; without it the Free Hit
    isn't ranked. Only one chip can be played per week, so if two chips' best weeks clash, the
    one that loses less by moving takes its next-best week."""
    first = gws[0]
    squad = state.element_ids
    outlooks = []
    for win in chips:
        weeks_in = [g for g in gws if win.covers(g)]
        if not weeks_in or win.start > first + LOOKAHEAD - 1:
            continue
        if win.name not in RANKED or (win.name == FREE_HIT and free_hit_pool is None):
            outlooks.append(ChipOutlook(win.name, win, (), None, False))
            continue
        weeks = []
        for g in weeks_in:
            x = {p: by_gw.get(g, 0.0) for p, by_gw in xpts.items()}
            if win.name == BENCH_BOOST:
                value, players = bench_boost_week(squad, position, x)
            elif win.name == TRIPLE_CAPTAIN:
                value, players = triple_captain_week(squad, position, x)
            else:
                value, players, _ = free_hit_week(free_hit_pool(g), state, g, discount=discount)
            weeks.append(ChipWeek(g, round(value, 2), players))
        best, now, close = decide(weeks, first)
        outlooks.append(ChipOutlook(win.name, win, tuple(weeks), best, now, close))
    return _one_chip_per_week(outlooks, first)


def _one_chip_per_week(outlooks: list[ChipOutlook], first: int) -> list[ChipOutlook]:
    taken: dict[int, int] = {}  # gw -> index of the outlook that has it
    for i in sorted((i for i, o in enumerate(outlooks) if o.best_gw is not None), key=lambda i: -outlooks[i].best.xpts):
        o = outlooks[i]
        if o.best_gw not in taken:
            taken[o.best_gw] = i
            continue
        j = taken[o.best_gw]
        # Whoever loses less by moving to their next free week moves.
        def next_best(k: int) -> ChipWeek | None:
            return next((w for w in outlooks[k].ranked() if w.gw not in taken and w.gw != o.best_gw), None)

        mine, theirs = next_best(i), next_best(j)
        loss_mine = o.best.xpts - (mine.xpts if mine else 0.0)
        loss_theirs = outlooks[j].best.xpts - (theirs.xpts if theirs else 0.0)
        mover, alt = (i, mine) if loss_mine <= loss_theirs else (j, theirs)
        if mover == j:
            taken[o.best_gw] = i
        if alt is not None:
            m = outlooks[mover]
            close = tuple(w.gw for w in m.weeks if w.gw not in (alt.gw, o.best_gw) and alt.xpts - w.xpts <= CLOSE)
            outlooks[mover] = replace(m, best_gw=alt.gw, play_now=alt.gw == first, close=close)
            taken[alt.gw] = mover
    return outlooks


def fixture_counts(fixtures: Iterable[tuple[int | None, int, int]], teams: Iterable[int], gws: Iterable[int]) -> dict[int, tuple[list[int], list[int]]]:
    """gw -> (teams with no match, teams with two or more), from (event, home, away) tuples."""
    teams = list(teams)
    counts: dict[int, dict[int, int]] = {g: {t: 0 for t in teams} for g in gws}
    for event, home, away in fixtures:
        if event in counts:
            counts[event][home] += 1
            counts[event][away] += 1
    return {g: ([t for t, n in c.items() if n == 0], [t for t, n in c.items() if n > 1]) for g, c in counts.items()}


__all__ = [
    "ADVISED", "BENCH_BOOST", "CLOSE", "FREE_HIT", "FREE_HIT_BUY_DISCOUNT", "LOOKAHEAD", "TRIPLE_CAPTAIN", "WILDCARD",
    "ChipOutlook", "ChipWeek", "bench_boost_week", "chip_outlook", "decide", "fixture_counts", "free_hit_week",
    "triple_captain_week",
]
