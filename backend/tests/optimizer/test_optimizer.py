"""Phase 3 gate: valid squads every time, under 5 s. Plus the spec's sanity checks."""

import random
import time
from dataclasses import replace

import pytest

from app.fpl.models import EntryPicks
from app.model.history import SeasonData
from app.model.project import project
from app.optimizer.inputs import build_pool
from app.optimizer.ownership import LeagueOwnership, league_ownership
from app.optimizer.plans import PlanSet, make_plans, validate
from app.optimizer.solver import (
    MAX_PER_CLUB, SQUAD_BY_POSITION, STRATEGY_WEIGHTS, PoolPlayer, Settings, solve,
)
from app.optimizer.state import OwnedPlayer, SquadState

HAALAND = 411
GWS = (11, 12, 13, 14)
TRAIN_THROUGH = 9


@pytest.fixture(scope="module")
def projection(season: SeasonData):
    return project(season, train_through=TRAIN_THROUGH, target_gws=GWS)


@pytest.fixture(scope="module")
def pool(season: SeasonData, projection, manager_state: SquadState) -> list[PoolPlayer]:
    return build_pool(season.bootstrap, projection, manager_state, GWS)


@pytest.fixture(scope="module")
def ownership(rival_picks: list[EntryPicks]) -> LeagueOwnership:
    return league_ownership(rival_picks)


@pytest.fixture(scope="module")
def plan_sets(pool, manager_state, ownership) -> dict[str, PlanSet]:
    return {
        strategy: make_plans(pool, manager_state, Settings(GWS, strategy=strategy, max_hits=1), ownership)
        for strategy in STRATEGY_WEIGHTS
    }


def _players(pool: list[PoolPlayer]) -> dict[int, PoolPlayer]:
    return {p.element: p for p in pool}


# ---- the gate -----------------------------------------------------------------------------


@pytest.mark.parametrize("strategy", list(STRATEGY_WEIGHTS))
def test_real_squad_plans_are_valid(plan_sets, pool, manager_state, strategy: str) -> None:
    ps = plan_sets[strategy]
    assert len(ps.plans) == 3
    for plan in ps.plans:
        assert validate(plan.solution, _players(pool), manager_state, ps.settings) == []
        assert plan.hits <= 1


def test_whole_run_is_under_five_seconds(season, manager_state, ownership) -> None:
    """Projection + pool + three plans, the way a request would run them."""
    started = time.perf_counter()
    proj = project(season, train_through=TRAIN_THROUGH, target_gws=GWS)
    pool = build_pool(season.bootstrap, proj, manager_state, GWS)
    make_plans(pool, manager_state, Settings(GWS, strategy="protect", max_hits=1), ownership)
    assert time.perf_counter() - started < 5.0


def _random_state(pool: list[PoolPlayer], rng: random.Random, entry_id: int) -> SquadState:
    """A random valid 15-man squad within £100m, with random bank and free transfers."""
    while True:
        chosen: list[PoolPlayer] = []
        clubs: dict[int, int] = {}
        for pos, n in SQUAD_BY_POSITION.items():
            options = [p for p in pool if p.position == pos]
            rng.shuffle(options)
            for p in options:
                if sum(c.position == pos for c in chosen) == n:
                    break
                if clubs.get(p.team, 0) < MAX_PER_CLUB:
                    chosen.append(p)
                    clubs[p.team] = clubs.get(p.team, 0) + 1
        cost = sum(p.buy_price for p in chosen)
        if len(chosen) == 15 and cost <= 1000:
            players = tuple(OwnedPlayer(p.element, p.buy_price, p.buy_price) for p in chosen)
            return SquadState(entry_id, 10, players, rng.randint(0, 1000 - cost), rng.randint(1, 5))


@pytest.mark.parametrize("seed", range(6))
def test_random_squads_always_get_valid_plans(pool, ownership, seed: int) -> None:
    rng = random.Random(seed)
    state = _random_state(pool, rng, entry_id=seed)
    strategy = list(STRATEGY_WEIGHTS)[seed % 3]
    settings = Settings(GWS, strategy=strategy, max_hits=seed % 3)
    random_pool = [replace(p, sell_price=p.buy_price) for p in pool]  # the random squad paid today's prices
    sol = solve(random_pool, state, settings, ownership)
    assert sol is not None
    assert validate(sol, _players(random_pool), state, settings) == []


# ---- sanity checks ------------------------------------------------------------------------


@pytest.mark.parametrize("strategy", ["protect", "balanced"])
def test_top_premium_is_not_sold(plan_sets, strategy: str) -> None:
    """The v0 Haaland bug: don't sell the top-projected premium to fund mid-price players."""
    for plan in plan_sets[strategy].plans:
        for gw in plan.solution.gameweeks:
            assert HAALAND not in gw.transfers_out


def test_premium_is_sold_when_the_numbers_clearly_justify_it(pool, manager_state) -> None:
    """If Haaland is projected 0 (e.g. left the club), selling him is the obvious move."""
    gone = [replace(p, xpts={g: 0.0 for g in GWS}) if p.element == HAALAND else p for p in pool]
    sol = solve(gone, manager_state, Settings(GWS, strategy="protect", max_hits=0))
    assert HAALAND in sol.first.transfers_out


def test_protect_maximises_points_and_captains_the_top_projection(plan_sets, pool) -> None:
    players = _players(pool)
    for gw in plan_sets["protect"].plans[0].solution.gameweeks:
        assert gw.captain == max(gw.starting, key=lambda p: players[p].xpts[gw.gw])


@pytest.mark.parametrize("strategy", list(STRATEGY_WEIGHTS))
def test_do_no_harm(plan_sets, strategy: str) -> None:
    for plan in plan_sets[strategy].plans:
        assert plan.xpts_gain >= -1e-6


def test_riskier_strategies_trade_points_for_differentials(plan_sets) -> None:
    protect, risky = plan_sets["protect"].plans[0], plan_sets["risky"].plans[0]
    assert protect.xpts_gain >= risky.xpts_gain
    assert risky.differential_gain >= protect.differential_gain


def test_plans_have_different_first_week_moves(plan_sets) -> None:
    for ps in plan_sets.values():
        firsts = {(frozenset(p.solution.first.transfers_in), frozenset(p.solution.first.transfers_out)) for p in ps.plans}
        assert len(firsts) == len(ps.plans)


def test_hit_buys_start(pool, manager_state) -> None:
    """Force a hit: one free transfer, a big incentive to make two transfers."""
    state = replace(manager_state, free_transfers=1)
    settings = Settings(GWS, strategy="protect", max_hits=1, hit_cost=0)  # free hits, so it takes one
    sol = solve(pool, state, settings)
    first = sol.first
    assert first.hits >= 1
    benched_buys = set(first.transfers_in) - set(first.starting)
    assert len(benched_buys) <= len(first.transfers_in) - first.hits


def test_max_hits_zero_means_no_hits(pool, manager_state) -> None:
    sol = solve(pool, replace(manager_state, free_transfers=1), Settings(GWS, strategy="protect", max_hits=0))
    assert sol.total_hits == 0
    assert all(len(g.transfers_in) <= g.free_transfers for g in sol.gameweeks)


def test_roll_is_offered_when_transfers_gain_nothing(pool, manager_state) -> None:
    flat = [replace(p, xpts={g: 2.0 for g in GWS}) for p in pool]
    ps = make_plans(flat, manager_state, Settings(GWS, strategy="protect", max_hits=0))
    assert any(p.is_roll for p in ps.plans)


def test_validate_catches_broken_plans(plan_sets, pool, manager_state) -> None:
    ps = plan_sets["protect"]
    sol = ps.plans[0].solution
    gw = sol.gameweeks[0]
    bad_captain = replace(gw, captain=gw.bench[0])
    broken = replace(sol, gameweeks=(bad_captain, *sol.gameweeks[1:]))
    assert any("captain" in e for e in validate(broken, _players(pool), manager_state, ps.settings))
    overspent = replace(sol, gameweeks=(replace(gw, bank=gw.bank + 1), *sol.gameweeks[1:]))
    assert any("bank" in e for e in validate(overspent, _players(pool), manager_state, ps.settings))


def test_transfers_pair_like_for_like(plan_sets, pool) -> None:
    from app.optimizer.plans import paired_transfers

    players = _players(pool)
    for ps in plan_sets.values():
        for plan in ps.plans:
            for gw in plan.solution.gameweeks:
                pairs = paired_transfers(gw, players)
                assert len(pairs) == len(gw.transfers_in)
                assert all(players[o].position == players[i].position for o, i in pairs)


# ---- bench and free transfers (Nikhil's feedback, 8 Nov 2026) ------------------------------


def _bench_gk(sol, pool) -> int:
    players = _players(pool)
    return next(p for p in sol.squad if players[p].position == 1 and p not in sol.starting)


def test_no_transfer_is_spent_on_the_backup_keeper(plan_sets, pool, manager_state) -> None:
    """A backup keeper never plays, so no plan should buy one to sit on the bench."""
    players = _players(pool)
    for ps in plan_sets.values():
        for plan in ps.plans:
            for gw in plan.solution.gameweeks:
                for p in gw.transfers_in:
                    if players[p].position == 1:
                        assert p in gw.starting, f"GW{gw.gw}: bought keeper {p} for the bench"


def test_a_tiny_gain_is_not_worth_a_free_transfer(pool, manager_state) -> None:
    """With one free transfer and a one-week horizon, a move must beat the value of saving it."""
    gw = GWS[:1]
    keep = solve(pool, manager_state, Settings(gw, strategy="protect"), no_transfers=True)
    best = solve(pool, manager_state, Settings(gw, strategy="protect"))
    plan_xpts = lambda s: sum(_players(pool)[p].xpts.get(gw[0], 0) for p in s.first.starting) + _players(pool)[s.first.captain].xpts.get(gw[0], 0)
    if best.first.transfers_in:
        assert plan_xpts(best) - plan_xpts(keep) >= Settings(gw).ft_value - 1e-6
    # And with saving made worthless, the solver is free to make smaller moves again.
    loose = solve(pool, manager_state, Settings(gw, strategy="protect", ft_value=0.0))
    assert plan_xpts(loose) >= plan_xpts(best) - 1e-6


def test_a_timed_out_do_nothing_plan_is_dropped(pool, manager_state, monkeypatch) -> None:
    """On a slow server a later solve can time out and return its warm start (keep the squad).
    That isn't a real plan, so it's dropped rather than shown as 'roll, +0.0'."""
    import app.optimizer.plans as plans_mod

    real_solve = plans_mod.solve

    def slow_solve(*args, cuts=(), warm_start=None, **kwargs):
        if len(cuts) == 2 and warm_start is not None:  # the third plan in the chain "times out"
            return replace(warm_start, proven_optimal=False)
        return real_solve(*args, cuts=cuts, warm_start=warm_start, **kwargs)

    monkeypatch.setattr(plans_mod, "solve", slow_solve)
    ps = make_plans(pool, manager_state, Settings(GWS, strategy="protect"))
    assert len(ps.plans) == 2
    assert all(p.xpts_gain > 0 for p in ps.plans)


def test_hit_margin_only_takes_hits_that_clear_it(pool, manager_state) -> None:
    """A margin raises the bar for hits (decision only); reported points still count 4 per hit."""
    loose = solve(pool, manager_state, Settings(GWS, strategy="protect", max_hits=3, time_limit=20))
    strict = solve(pool, manager_state, Settings(GWS, strategy="protect", max_hits=3, hit_margin=100.0, time_limit=20))
    assert strict.total_hits == 0
    assert loose.total_hits >= strict.total_hits
