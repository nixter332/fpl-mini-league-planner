"""One multi-week MILP: transfers, lineup and captain for every GW in the horizon.

Rules are in docs/v0-lessons.md -> Keep. The objective (docs/SPEC.md -> Optimizer, with the
ownership split agreed with Nikhil):

    maximise  sum_g decay^g * sum_p xPts[p,g] * ( (1 - w*start_p) * start[p,g]
                                                 + (1 - w*captain_p) * captain[p,g]
                                                 + bench_weight_p * (squad[p,g] - start[p,g]) )
              - hit_cost * sum_g hits[g]
              + ft_value * free transfers still held after the last GW

bench_weight_p is 0 for goalkeepers: a backup keeper almost never plays, so upgrading him is
worth nothing. Without ft_value a spare free transfer looked free, so the solver spent it on
bench upgrades (Nikhil, 8 Nov 2026: "I don't want to waste a transfer on a player I never use").

w is the strategy weight: Protect 0 (pure points), Balanced 0.15, Risky 0.33. The vice-captain is
picked after solving as the best other starter (keeping him out of the MILP makes it faster).

Solver: CBC (bundled with PuLP). On this model it was 3-5x faster than HiGHS (~1 s vs ~5 s
per solve), which is what keeps a full set of plans under the 5 s target.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

import os
import tempfile
import uuid

import pulp

from app.model.scoring import DEF, FWD, GKP, MID
from app.optimizer.ownership import NO_RIVALS, LeagueOwnership
from app.optimizer.state import MAX_FREE_TRANSFERS, SquadState

# Gentler than the original spec (0 / 0.5 / 1): at 0.5+ the solver gave up real points in
# Nikhil's league, and at 1 it benched template players. Agreed with Nikhil 2026-11-08.
STRATEGY_WEIGHTS = {"protect": 0.0, "balanced": 0.15, "risky": 0.33}
SQUAD_SIZE = 15
XI_SIZE = 11
SQUAD_BY_POSITION = {GKP: 2, DEF: 5, MID: 5, FWD: 3}
XI_MIN = {GKP: 1, DEF: 3, MID: 2, FWD: 1}
XI_MAX = {GKP: 1, DEF: 5, MID: 5, FWD: 3}
MAX_PER_CLUB = 3


@dataclass(frozen=True)
class PoolPlayer:
    element: int
    position: int
    team: int
    buy_price: int  # current price
    sell_price: int  # what selling him raises now (owned players: the derived sell price)
    xpts: dict[int, float]  # by GW


@dataclass(frozen=True)
class Settings:
    gws: tuple[int, ...]
    strategy: str = "balanced"
    max_hits: int = 0  # total over the whole horizon, not per GW
    decay: float = 0.9
    bench_weight: float = 0.1  # outfield subs only; backup goalkeepers count 0
    ft_value: float = 1.5  # xPts per free transfer still held after the horizon
    hit_cost: int = 4
    max_free_transfers: int = MAX_FREE_TRANSFERS
    time_limit: float = 20.0  # per solve; make_plans sets tighter limits from its budget

    @property
    def weight(self) -> float:
        return STRATEGY_WEIGHTS[self.strategy]


@dataclass(frozen=True)
class Cut:
    """Forbid this exact set of transfers in the first GW (used to find the next-best plan)."""

    transfers_in: frozenset[int]
    transfers_out: frozenset[int]


@dataclass(frozen=True)
class GameweekSolution:
    gw: int
    transfers_in: tuple[int, ...]
    transfers_out: tuple[int, ...]
    free_transfers: int  # available going into this GW
    hits: int
    bank: int  # after this GW's transfers
    squad: tuple[int, ...]
    starting: tuple[int, ...]
    bench: tuple[int, ...]  # in FPL order: backup GK first, then outfield by xPts
    captain: int
    vice: int


@dataclass(frozen=True)
class Solution:
    gameweeks: tuple[GameweekSolution, ...]
    objective: float
    solve_seconds: float = 0.0
    proven_optimal: bool = True  # False if the solver hit its time limit (best found so far)

    @property
    def first(self) -> GameweekSolution:
        return self.gameweeks[0]

    @property
    def total_hits(self) -> int:
        return sum(g.hits for g in self.gameweeks)


class InfeasibleError(RuntimeError):
    pass


def solve(
    pool: Sequence[PoolPlayer],
    state: SquadState,
    settings: Settings,
    ownership: LeagueOwnership = NO_RIVALS,
    *,
    cuts: Iterable[Cut] = (),
    no_transfers_first_gw: bool = False,
    no_transfers: bool = False,
    warm_start: Solution | None = None,
    min_xpts: float | None = None,
) -> Solution | None:
    """Best plan under the settings, or None if the cuts leave nothing feasible.

    `warm_start` is any valid plan for the same pool and state (e.g. "keep the squad").
    `min_xpts` is the do-no-harm floor: the plan's undiscounted XI + captain xPts minus hit
    costs must be at least this (make_plans passes the no-transfers baseline).
    """
    players = {p.element: p for p in pool}
    missing = state.element_ids - set(players)
    if missing:
        raise ValueError(f"Pool must contain the whole current squad; missing {sorted(missing)}")

    P, G = list(players), list(settings.gws)
    owned = state.element_ids
    w = settings.weight
    # CBC on Windows only reads a warm start when PuLP keeps its files, which it names after
    # the problem; a unique temp path keeps parallel solves apart. We delete the files after.
    work_prefix = os.path.join(tempfile.gettempdir(), f"fplplan_{uuid.uuid4().hex}")
    prob = pulp.LpProblem(work_prefix, pulp.LpMaximize)

    def binaries(name: str) -> dict:
        return {(p, g): prob.add_variable(f"{name}_{p}_{g}", cat="Binary") for p in P for g in G}

    squad, start, cap = binaries("squad"), binaries("start"), binaries("cap")
    # Transfers follow from squad changes, so they needn't be integer: with `squad` and the
    # previous squad binary, the constraints below force buy/sell to 0 or 1.
    buy = {(p, g): prob.add_variable(f"in_{p}_{g}", 0, 1) for p in P for g in G}
    sell = {(p, g): prob.add_variable(f"out_{p}_{g}", 0, 1) for p in P for g in G}
    benched_buy = {(p, g): prob.add_variable(f"bb_{p}_{g}", 0, 1) for p in P for g in G}
    ft = {g: prob.add_variable(f"ft_{g}", 0, settings.max_free_transfers) for g in G}
    hits = {g: prob.add_variable(f"hits_{g}", 0, SQUAD_SIZE, cat="Integer") for g in G}
    took_hit = {g: prob.add_variable(f"took_hit_{g}", cat="Binary") for g in G}
    bank = {g: prob.add_variable(f"bank_{g}", 0) for g in G}

    # Free transfers carried past the horizon (same rule as between GWs; maximising keeps it tight)
    g_last = G[-1]
    ft_end = prob.add_variable("ft_end", 0, settings.max_free_transfers)
    prob += ft_end <= ft[g_last] - (pulp.lpSum(buy[p, g_last] for p in P) - hits[g_last]) + 1

    # Objective
    terms = []
    for k, g in enumerate(G):
        d = settings.decay**k
        for p in P:
            x = players[p].xpts.get(g, 0.0)
            start_w = 1 - w * min(ownership.start_share(p), 1.0)
            cap_w = 1 - w * min(ownership.captain_share(p), 1.0)
            bench_w = 0.0 if players[p].position == GKP else settings.bench_weight
            terms.append(
                d * x * (start_w * start[p, g] + cap_w * cap[p, g] + bench_w * (squad[p, g] - start[p, g]))
            )
    prob += pulp.lpSum(terms) - settings.hit_cost * pulp.lpSum(hits.values()) + settings.ft_value * ft_end

    for k, g in enumerate(G):
        n_transfers = pulp.lpSum(buy[p, g] for p in P)
        for p in P:
            prev = (1 if p in owned else 0) if k == 0 else squad[p, G[k - 1]]
            prob += squad[p, g] == prev + buy[p, g] - sell[p, g]
            prob += buy[p, g] <= 1 - prev
            prob += sell[p, g] <= prev
            prob += start[p, g] <= squad[p, g]
            prob += cap[p, g] <= start[p, g]
            prob += benched_buy[p, g] >= buy[p, g] - start[p, g]

        # Squad shape and lineup
        prob += pulp.lpSum(squad[p, g] for p in P) == SQUAD_SIZE
        prob += pulp.lpSum(start[p, g] for p in P) == XI_SIZE
        for pos, count in SQUAD_BY_POSITION.items():
            in_pos = [p for p in P if players[p].position == pos]
            prob += pulp.lpSum(squad[p, g] for p in in_pos) == count
            prob += pulp.lpSum(start[p, g] for p in in_pos) >= XI_MIN[pos]
            prob += pulp.lpSum(start[p, g] for p in in_pos) <= XI_MAX[pos]
        for club in {pl.team for pl in players.values()}:
            prob += pulp.lpSum(squad[p, g] for p in P if players[p].team == club) <= MAX_PER_CLUB
        prob += pulp.lpSum(cap[p, g] for p in P) == 1

        # Budget, with sell prices for players owned now and current price for anyone bought later
        prev_bank = state.bank if k == 0 else bank[G[k - 1]]
        prob += bank[g] == prev_bank + pulp.lpSum(
            players[p].sell_price * sell[p, g] - players[p].buy_price * buy[p, g] for p in P
        )

        # Free transfers and hits: hits = max(0, transfers - free), exactly
        if k == 0:
            prob += ft[g] == min(state.free_transfers, settings.max_free_transfers)
        else:
            gp = G[k - 1]
            free_used_prev = pulp.lpSum(buy[p, gp] for p in P) - hits[gp]
            prob += ft[g] <= ft[gp] - free_used_prev + 1
        prob += hits[g] >= n_transfers - ft[g]
        prob += hits[g] <= SQUAD_SIZE * took_hit[g]
        prob += hits[g] <= n_transfers - ft[g] + (SQUAD_SIZE + MAX_FREE_TRANSFERS) * (1 - took_hit[g])
        # Players bought with a hit must start: benched buys can only use free transfers
        prob += pulp.lpSum(benched_buy[p, g] for p in P) <= n_transfers - hits[g]

        if no_transfers or (no_transfers_first_gw and k == 0):
            prob += n_transfers == 0

    prob += pulp.lpSum(hits.values()) <= settings.max_hits

    if min_xpts is not None:
        plan_xpts = pulp.lpSum(players[p].xpts.get(g, 0.0) * (start[p, g] + cap[p, g]) for p in P for g in G)
        prob += plan_xpts - settings.hit_cost * pulp.lpSum(hits.values()) >= min_xpts - 1e-6

    g0 = G[0]
    for cut in cuts:
        same = [buy[p, g0] for p in cut.transfers_in] + [sell[p, g0] for p in cut.transfers_out]
        other = [buy[p, g0] for p in P if p not in cut.transfers_in] + [sell[p, g0] for p in P if p not in cut.transfers_out]
        prob += pulp.lpSum(same) - pulp.lpSum(other) <= len(same) - 1

    if warm_start is not None:
        _set_initial_values(warm_start, P, G, squad, start, cap, buy, sell, benched_buy, ft, hits, took_hit, bank)
    solver = pulp.PULP_CBC_CMD(msg=False, timeLimit=settings.time_limit, warmStart=warm_start is not None, keepFiles=True)
    try:
        prob.solve(solver)
    finally:
        for ext in ("lp", "mps", "sol", "mst"):
            try:
                os.remove(f"{work_prefix}-pulp.{ext}")
            except FileNotFoundError:
                pass
    status = pulp.LpStatus[prob.status]
    if status == "Infeasible" or prob.sol_status == pulp.LpSolutionNoSolutionFound:
        return None
    if status != "Optimal":
        raise InfeasibleError(f"Solver finished with status {status}")
    proven = prob.sol_status == pulp.LpSolutionOptimal

    def on(var: pulp.LpVariable) -> bool:
        return (var.value() or 0) > 0.5

    gameweeks = []
    ft_now = min(state.free_transfers, settings.max_free_transfers)
    for g in G:
        squad_g = tuple(p for p in P if on(squad[p, g]))
        starting = tuple(sorted((p for p in squad_g if on(start[p, g])), key=lambda p: (players[p].position, -players[p].xpts.get(g, 0))))
        bench_pool = [p for p in squad_g if p not in starting]
        bench = tuple(sorted(bench_pool, key=lambda p: (players[p].position != GKP, -players[p].xpts.get(g, 0))))
        gameweeks.append(
            GameweekSolution(
                gw=g,
                transfers_in=tuple(p for p in P if on(buy[p, g])),
                transfers_out=tuple(p for p in P if on(sell[p, g])),
                free_transfers=ft_now,
                hits=int(round(hits[g].value())),
                bank=int(round(bank[g].value())),
                squad=squad_g,
                starting=starting,
                bench=bench,
                captain=next(p for p in starting if on(cap[p, g])),
                vice=max((p for p in starting if not on(cap[p, g])), key=lambda p: players[p].xpts.get(g, 0.0)),
            )
        )
        # The ft variable is only bounded above, so recompute the real count by replay.
        free_used = len(gameweeks[-1].transfers_in) - gameweeks[-1].hits
        ft_now = min(ft_now - free_used + 1, settings.max_free_transfers)
    return Solution(tuple(gameweeks), float(pulp.value(prob.objective)), float(prob.solutionTime), proven)


def _set_initial_values(ws: Solution, P, G, squad, start, cap, buy, sell, benched_buy, ft, hits, took_hit, bank) -> None:
    by_gw = {g.gw: g for g in ws.gameweeks}
    for g in G:
        sol = by_gw[g]
        in_squad, starters = set(sol.squad), set(sol.starting)
        ins, outs = set(sol.transfers_in), set(sol.transfers_out)
        for p in P:
            squad[p, g].setInitialValue(int(p in in_squad))
            start[p, g].setInitialValue(int(p in starters))
            cap[p, g].setInitialValue(int(p == sol.captain))
            buy[p, g].setInitialValue(int(p in ins))
            sell[p, g].setInitialValue(int(p in outs))
            benched_buy[p, g].setInitialValue(int(p in ins and p not in starters))
        ft[g].setInitialValue(sol.free_transfers)
        hits[g].setInitialValue(sol.hits)
        took_hit[g].setInitialValue(int(sol.hits > 0))
        bank[g].setInitialValue(sol.bank)
