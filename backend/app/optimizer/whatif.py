"""What-if: score a manager's own transfers with the planner's rules and points.

The user lists moves per gameweek (and optionally a captain and a chip per week). Each move is
checked as FPL would: the player out must be in the squad, the player in must not be, positions
must match, at most 3 per club, and the bank can't go negative. A move that breaks a rule is
skipped and reported in plain words; the rest still apply. The result is a Solution like the
solver's, so validate() and score() give numbers that match the planner's exactly.
"""

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from app.model.scoring import DEF, FWD, GKP, MID
from app.optimizer.chips import BENCH_BOOST, CHIP_LABELS, FREE_HIT, TRANSFER_CHIPS, TRIPLE_CAPTAIN, window_for
from app.optimizer.lineup import best_lineup
from app.optimizer.plans import validate
from app.optimizer.solver import MAX_PER_CLUB, GameweekSolution, PoolPlayer, Settings, Solution
from app.optimizer.state import SquadState

POSITION_NAMES = {1: "goalkeeper", 2: "defender", 3: "midfielder", 4: "forward"}
# Our planner never benches a player bought with a hit; FPL allows it, so the sandbox does too.
PLANNER_ONLY_RULES = ("bought with a hit is on the bench",)


@dataclass(frozen=True)
class Move:
    gw: int
    out: int
    into: int


@dataclass(frozen=True)
class Swap:
    """The user's lineup choice for a week: `bench` goes to the bench, `start` comes into the XI."""

    gw: int
    bench: int
    start: int


XI_MIN = {GKP: 1, DEF: 3, MID: 2, FWD: 1}
XI_MAX = {GKP: 1, DEF: 5, MID: 5, FWD: 3}
POSITION_PLURAL = {GKP: "goalkeeper", DEF: "defenders", MID: "midfielders", FWD: "forward"}


@dataclass(frozen=True)
class Problem:
    gw: int | None
    message: str


def money(tenths: int) -> str:
    return f"£{tenths / 10:.1f}m"


def build_plan(
    state: SquadState,
    players: Mapping[int, PoolPlayer],
    names: Mapping[int, str],
    settings: Settings,
    moves: Iterable[Move] = (),
    captains: Mapping[int, int] | None = None,
    chips: Mapping[int, str] | None = None,
    swaps: Iterable[Swap] = (),
) -> tuple[Solution, list[Problem]]:
    """The user's plan over settings.gws, with every move that breaks a rule skipped and reported.
    Each week starts from the best XI; the user's swaps (bench one, start another) apply on top."""
    captains, chips = captains or {}, chips or {}
    swaps_by_gw: dict[int, list[Swap]] = {}
    for sw in swaps:
        swaps_by_gw.setdefault(sw.gw, []).append(sw)
    problems: list[Problem] = []
    by_gw: dict[int, list[Move]] = {}
    for m in moves:
        by_gw.setdefault(m.gw, []).append(m)
    for gw in sorted(set(by_gw) - set(settings.gws)):
        problems.append(Problem(gw, f"GW{gw} isn't in this plan."))

    kept = set(state.element_ids)  # the squad that carries on (a Free Hit week doesn't change it)
    bank = state.bank
    ft = min(state.free_transfers, settings.max_free_transfers)
    sell = {p.element: p.sell_price for p in state.players}
    used_windows = set()
    weeks: list[GameweekSolution] = []

    for gw in settings.gws:
        tag = f"GW{gw}"
        chip = chips.get(gw)
        if chip is not None:
            window = window_for(state.chips, chip, gw)
            if window is None or window in used_windows:
                problems.append(Problem(gw, f"{tag}: you don't have a {CHIP_LABELS.get(chip, chip)} to play this week."))
                chip = None
            else:
                used_windows.add(window)

        squad = set(kept)
        week_bank = bank
        ins: list[int] = []
        outs: list[int] = []
        for m in by_gw.get(gw, []):
            name_out, name_in = names.get(m.out, f"#{m.out}"), names.get(m.into, f"#{m.into}")
            if m.out not in squad:
                problems.append(Problem(gw, f"{tag}: {name_out} isn't in your squad."))
                continue
            if m.into not in players:
                problems.append(Problem(gw, f"{tag}: {name_in} can't be bought."))
                continue
            if m.into in squad:
                problems.append(Problem(gw, f"{tag}: {name_in} is already in your squad."))
                continue
            p_out, p_in = players[m.out], players[m.into]
            if p_out.position != p_in.position:
                problems.append(Problem(gw, f"{tag}: {name_out} is a {POSITION_NAMES[p_out.position]}, so he can only be swapped for another."))
                continue
            after = (squad - {m.out}) | {m.into}
            clubs = Counter(players[p].team for p in after)
            if clubs[p_in.team] > MAX_PER_CLUB:
                problems.append(Problem(gw, f"{tag}: bringing in {name_in} would give you more than {MAX_PER_CLUB} players from one club."))
                continue
            new_bank = week_bank + sell.get(m.out, p_out.sell_price) - p_in.buy_price
            if new_bank < 0:
                problems.append(Problem(gw, f"{tag}: {name_in} costs {money(-new_bank)} more than you have."))
                continue
            squad, week_bank = after, new_bank
            if m.out in ins:  # bought and sold in the same week: it was never really bought
                ins.remove(m.out)
            else:
                outs.append(m.out)
            ins.append(m.into)

        hits = 0 if chip in TRANSFER_CHIPS else max(0, len(ins) - ft)
        xpts = {p: players[p].xpts.get(gw, 0.0) for p in squad}
        lineup = best_lineup(squad, {p: players[p].position for p in squad}, xpts)
        xi, bench = list(lineup.starting), list(lineup.bench)
        for sw in swaps_by_gw.get(gw, []):
            problem = _swap_problem(sw, xi, bench, players, names)
            if problem:
                problems.append(Problem(gw, f"{tag}: {problem}"))
                continue
            xi[xi.index(sw.bench)] = sw.start
            bench[bench.index(sw.start)] = sw.bench
        bench.sort(key=lambda p: (players[p].position != GKP, -xpts[p]))  # FPL order: keeper first
        by_xpts = sorted(xi, key=lambda p: -xpts[p])
        captain, vice = by_xpts[0], by_xpts[1]
        wanted = captains.get(gw)
        if wanted is not None:
            if wanted in xi:
                captain = wanted
                vice = max((p for p in xi if p != captain), key=lambda p: xpts[p])
            else:
                problems.append(Problem(gw, f"{tag}: {names.get(wanted, f'#{wanted}')} isn't in your starting XI, so he can't be captain."))
        weeks.append(GameweekSolution(
            gw=gw, transfers_in=tuple(ins), transfers_out=tuple(outs), free_transfers=ft, hits=hits,
            bank=bank if chip == FREE_HIT else week_bank, squad=tuple(sorted(squad)),
            starting=tuple(xi), bench=tuple(bench), captain=captain, vice=vice, chip=chip,
        ))
        if chip == FREE_HIT:
            continue  # squad, bank and free transfers come back unchanged
        kept, bank = squad, week_bank
        for p in ins:
            sell[p] = players[p].buy_price
        if chip not in TRANSFER_CHIPS:
            ft = min(ft - (len(ins) - hits) + 1, settings.max_free_transfers)

    solution = Solution(tuple(weeks), objective=0.0)
    errors = [e for e in validate(solution, dict(players), state, _no_hit_cap(settings)) if not any(r in e for r in PLANNER_ONLY_RULES)]
    problems += [Problem(None, f"Rule check: {e}") for e in errors]  # shouldn't happen: the checks above come first
    return solution, problems


def _swap_problem(sw: Swap, xi: list[int], bench: list[int], players: Mapping[int, PoolPlayer], names: Mapping[int, str]) -> str | None:
    """Why this lineup swap can't be made (None if it can)."""
    n_out, n_in = names.get(sw.bench, f"#{sw.bench}"), names.get(sw.start, f"#{sw.start}")
    if sw.bench not in xi:
        return f"{n_out} isn't in your starting XI this week."
    if sw.start not in bench:
        return f"{n_in} isn't on your bench this week."
    if (players[sw.bench].position == GKP) != (players[sw.start].position == GKP):
        return "a goalkeeper can only swap with the other goalkeeper."
    counts = Counter(players[p].position for p in xi)
    counts[players[sw.bench].position] -= 1
    counts[players[sw.start].position] += 1
    for pos, low in XI_MIN.items():
        if counts[pos] < low:
            return f"starting {n_in} for {n_out} leaves fewer than {low} {POSITION_PLURAL[pos]}."
        if counts[pos] > XI_MAX[pos]:
            return f"starting {n_in} for {n_out} gives you more than {XI_MAX[pos]} {POSITION_PLURAL[pos]}."
    return None


def _no_hit_cap(settings: Settings) -> Settings:
    """Users may take as many hits as they like in the sandbox (FPL has no cap)."""
    from dataclasses import replace

    return replace(settings, max_hits=99)


def week_points(gw: GameweekSolution, players: Mapping[int, PoolPlayer]) -> float:
    """Projected points for one week: XI + captain again (+ chip), minus hits."""
    x = lambda p: players[p].xpts.get(gw.gw, 0.0)
    total = sum(x(p) for p in gw.starting) + x(gw.captain)
    if gw.chip == TRIPLE_CAPTAIN:
        total += x(gw.captain)
    if gw.chip == BENCH_BOOST:
        total += sum(x(p) for p in gw.bench)
    return total - 4 * gw.hits
