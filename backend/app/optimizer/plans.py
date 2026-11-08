"""Top 3 transfer plans, each validated and scored against a "no transfers" baseline.

How plans are found: solve; forbid that plan's first-GW transfer set; solve again; repeat.
"Roll the transfer" (no transfers in the first GW) replaces plan 3 when it comes within
`roll_margin` of the best plan's objective and isn't already in the list.

Do no harm (agreed with Nikhil): every plan must be expected to score at least as many xPts
over the horizon as making no transfers with the best points-only lineups. This matters for
Balanced and Risky, which trade some points for differentials.
"""

from collections import Counter
import os
import time
from concurrent.futures import ThreadPoolExecutor
from collections.abc import Sequence
from dataclasses import dataclass, replace

from app.optimizer.ownership import NO_RIVALS, LeagueOwnership
from app.optimizer.solver import (
    MAX_PER_CLUB, SQUAD_BY_POSITION, SQUAD_SIZE, XI_MAX, XI_MIN, XI_SIZE,
    Cut, GameweekSolution, PoolPlayer, Settings, Solution, solve,
)
from app.optimizer.state import SquadState

ROLL_MARGIN = 1.5
# Solver time limits, tuned on a laptop core. A slower server sets SOLVER_TIME_SCALE (e.g. 3)
# so the solver gets enough time to find good plans there; see docs/deploy.md.
TIME_SCALE = float(os.environ.get("SOLVER_TIME_SCALE", "1"))
TIME_BUDGET = 3.5 * TIME_SCALE  # seconds for the whole set; the phase 3 gate is 5 s including projection
FIRST_PLAN_LIMIT = 2.0 * TIME_SCALE
MIN_SOLVE_LIMIT = 0.5 * TIME_SCALE


@dataclass(frozen=True)
class Plan:
    rank: int
    solution: Solution
    is_roll: bool
    xpts: float  # XI + captain over the horizon, minus hit costs (undiscounted)
    xpts_gain: float  # vs no transfers with the best points-only lineups and captains
    differential_xpts: float  # the share of xpts your rivals won't also get
    differential_gain: float

    @property
    def hits(self) -> int:
        return self.solution.total_hits


@dataclass(frozen=True)
class PlanSet:
    plans: tuple[Plan, ...]
    baseline: Solution  # best points-only lineups with no transfers (what "xpts_gain" compares to)
    settings: Settings
    seconds: float  # wall time to build and solve all plans


def make_plans(
    pool: Sequence[PoolPlayer],
    state: SquadState,
    settings: Settings,
    ownership: LeagueOwnership = NO_RIVALS,
    *,
    n_plans: int = 3,
    roll_margin: float = ROLL_MARGIN,
    budget: float = TIME_BUDGET,
) -> PlanSet:
    """Top plans within a time budget. Plan 1 gets up to FIRST_PLAN_LIMIT seconds (enough to
    prove optimality on typical squads); later plans share the rest. A plan that hits its limit
    is the best valid plan found so far (marked proven_optimal=False); all are validated."""
    started = time.perf_counter()
    players = {p.element: p for p in pool}
    points_only = replace(settings, strategy="protect")

    # The points-only "keep the squad" plan is the do-no-harm floor, and a valid warm start for
    # every other solve (it satisfies the floor with equality).
    baseline = solve(pool, state, points_only, ownership, no_transfers=True)
    assert baseline is not None, "keeping the current squad is always feasible"
    floor, _ = score(baseline, players, ownership, settings)
    deadline = started + budget

    def limited(seconds: float) -> Settings:
        return replace(settings, time_limit=max(seconds, MIN_SOLVE_LIMIT))

    with ThreadPoolExecutor(max_workers=1) as executor:
        # The "roll" plan doesn't depend on the top-plan chain, so it solves alongside it.
        roll_job = executor.submit(
            solve, pool, state, limited(FIRST_PLAN_LIMIT), ownership,
            no_transfers_first_gw=True, warm_start=baseline, min_xpts=floor,
        )

        solutions: list[Solution] = []
        cuts: list[Cut] = []
        for i in range(n_plans):
            remaining = deadline - time.perf_counter()
            limit = min(FIRST_PLAN_LIMIT, remaining) if i == 0 else remaining / (n_plans - i)
            # A cut can forbid "no transfers" (once a roll plan is found), so only warm-start before that.
            warm = baseline if not any(not c.transfers_in for c in cuts) else None
            sol = solve(pool, state, limited(limit), ownership, cuts=cuts, warm_start=warm, min_xpts=floor)
            if sol is None:
                break
            solutions.append(sol)
            cuts.append(Cut(frozenset(sol.first.transfers_in), frozenset(sol.first.transfers_out)))
        roll = roll_job.result()

    if solutions and roll is not None and not any(_is_roll(s) for s in solutions):
        if roll.objective >= solutions[0].objective - roll_margin:
            solutions = [*solutions[: n_plans - 1], roll]

    for sol in solutions:
        errors = validate(sol, players, state, settings)
        if errors:
            raise AssertionError(f"Solver returned an invalid plan: {errors}")

    base_x, base_d = score(baseline, players, ownership, settings)
    plans = []
    for rank, sol in enumerate(solutions, start=1):
        x, d = score(sol, players, ownership, settings)
        plans.append(Plan(rank, sol, _is_roll(sol), x, x - base_x, d, d - base_d))
    return PlanSet(tuple(plans), baseline, settings, time.perf_counter() - started)


def score(sol: Solution, players: dict[int, PoolPlayer], ownership: LeagueOwnership, settings: Settings) -> tuple[float, float]:
    """(xPts, differential xPts) over the horizon: starters + captain bonus, minus hits."""
    xpts = diff = 0.0
    for gw in sol.gameweeks:
        for p in gw.starting:
            x = players[p].xpts.get(gw.gw, 0.0)
            xpts += x
            diff += x * (1 - min(ownership.start_share(p), 1.0))
        cx = players[gw.captain].xpts.get(gw.gw, 0.0)
        xpts += cx
        diff += cx * (1 - min(ownership.captain_share(gw.captain), 1.0))
    hit_cost = settings.hit_cost * sol.total_hits
    return xpts - hit_cost, diff - hit_cost


def validate(sol: Solution, players: dict[int, PoolPlayer], state: SquadState, settings: Settings) -> list[str]:
    """Every FPL rule, checked independently of the solver. Empty list = valid."""
    errors: list[str] = []
    prev_squad = set(state.element_ids)
    bank = state.bank
    sell_prices = {p.element: p.sell_price for p in state.players}
    ft = min(state.free_transfers, settings.max_free_transfers)
    for gw in sol.gameweeks:
        tag = f"GW{gw.gw}"
        ins, outs = set(gw.transfers_in), set(gw.transfers_out)
        if ins & prev_squad or not outs <= prev_squad:
            errors.append(f"{tag}: transfers don't match the previous squad")
        squad = (prev_squad - outs) | ins
        if squad != set(gw.squad) or len(squad) != SQUAD_SIZE:
            errors.append(f"{tag}: squad is not 15 players")
        positions = Counter(players[p].position for p in squad)
        if any(positions[pos] != n for pos, n in SQUAD_BY_POSITION.items()):
            errors.append(f"{tag}: wrong squad positions {dict(positions)}")
        if any(n > MAX_PER_CLUB for n in Counter(players[p].team for p in squad).values()):
            errors.append(f"{tag}: more than {MAX_PER_CLUB} players from one club")
        xi = set(gw.starting)
        xi_pos = Counter(players[p].position for p in xi)
        if len(xi) != XI_SIZE or not xi <= squad:
            errors.append(f"{tag}: starting XI is not 11 squad players")
        if any(not XI_MIN[pos] <= xi_pos[pos] <= XI_MAX[pos] for pos in XI_MIN):
            errors.append(f"{tag}: invalid formation {dict(xi_pos)}")
        if set(gw.bench) != squad - xi:
            errors.append(f"{tag}: bench doesn't match squad minus XI")
        if gw.captain not in xi or gw.vice not in xi or gw.captain == gw.vice:
            errors.append(f"{tag}: captain and vice must be different starters")
        bank += sum(sell_prices.get(p, players[p].sell_price) for p in outs) - sum(players[p].buy_price for p in ins)
        if bank < 0 or bank != gw.bank:
            errors.append(f"{tag}: bank {bank} (solver says {gw.bank}) is negative or inconsistent")
        expected_hits = max(0, len(ins) - ft)
        if gw.hits != expected_hits or gw.free_transfers != ft:
            errors.append(f"{tag}: hits {gw.hits}/FT {gw.free_transfers}, expected {expected_hits}/{ft}")
        benched_buys = len(ins - xi)
        if benched_buys > len(ins) - gw.hits:
            errors.append(f"{tag}: a player bought with a hit is on the bench")
        free_used = len(ins) - gw.hits
        ft = min(ft - free_used + 1, settings.max_free_transfers)
        for p in ins:  # bought within the horizon: selling him later raises his current price
            sell_prices[p] = players[p].buy_price
        prev_squad = squad
    if sol.total_hits > settings.max_hits:
        errors.append(f"{sol.total_hits} hits is more than the max of {settings.max_hits}")
    return errors


def _is_roll(sol: Solution) -> bool:
    return not sol.first.transfers_in


def paired_transfers(gw: GameweekSolution, players: dict[int, PoolPlayer]) -> list[tuple[int, int]]:
    """(out, in) pairs, matched by position (FPL swaps are always like-for-like), then by price."""
    pairs: list[tuple[int, int]] = []
    for pos in sorted({players[p].position for p in gw.transfers_out}):
        outs = sorted((p for p in gw.transfers_out if players[p].position == pos), key=lambda p: -players[p].sell_price)
        ins = sorted((p for p in gw.transfers_in if players[p].position == pos), key=lambda p: -players[p].buy_price)
        pairs.extend(zip(outs, ins))
    return pairs
