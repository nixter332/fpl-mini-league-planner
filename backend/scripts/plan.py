"""Print the top 3 transfer plans for a manager.

Usage (from backend/):
    python -m scripts.plan --team 5179483 --league 1883627 --strategy balanced --horizon 4 --max-hits 0
    python -m scripts.plan --offline ...     # use the saved fixtures instead of the FPL API

--max-hits is the most -4 hits you'll accept over the whole horizon, not per gameweek.
Strategies: protect (pure points), balanced, risky (more differentials, more swing).
"""

import argparse
import sys
import time
from datetime import datetime, timezone

from app.fpl.client import FPLClient
from app.fpl.gameweeks import latest_finished_gameweek, latest_started_gameweek, next_actionable_gameweek
from app.fpl.models import Bootstrap, EntryHistory, EntryPicks, EventLive, Fixture, Transfer
from app.model.history import SeasonData
from app.model.project import project
from app.optimizer.inputs import build_pool, load_rival_picks, load_state, top_rivals
from app.optimizer.ownership import NO_RIVALS, LeagueOwnership, league_ownership
from app.optimizer.plans import Plan, PlanSet, make_plans, paired_transfers
from app.optimizer.solver import PoolPlayer
from app.optimizer.solver import STRATEGY_WEIGHTS, Settings
from app.optimizer.state import SquadState, build_state


def load_live(team: int, league: int | None, n_rivals: int) -> tuple[SeasonData, SquadState, LeagueOwnership, datetime]:
    now = datetime.now(timezone.utc)
    with FPLClient() as client:
        bootstrap = Bootstrap.model_validate(client.bootstrap())
        finished = latest_finished_gameweek(bootstrap.events)
        live = {gw: EventLive.model_validate(client.event_live(gw)) for gw in range(1, (finished.id if finished else 0) + 1)}
        fixtures = [Fixture.model_validate(f) for f in client.fixtures()]
        state = load_state(client, team, bootstrap, now)
        ownership = NO_RIVALS
        if league:
            rivals = top_rivals(client, league, team, n_rivals)
            ownership = league_ownership(load_rival_picks(client, rivals, state.picks_gw))
    return SeasonData(bootstrap, fixtures, live), state, ownership, now


def load_offline(team: int) -> tuple[SeasonData, SquadState, LeagueOwnership, datetime]:
    from scripts.backtest import FIXTURES, load_from_fixtures
    from tests.conftest import load_fixture

    manifest = load_fixture("manifest.json")
    if manifest["team_id"] != team:
        sys.exit(f"The saved fixtures are for team {manifest['team_id']}; run without --offline for other teams.")
    data = load_from_fixtures(FIXTURES)
    files = manifest["files"]
    state = build_state(
        team, EntryPicks.model_validate(load_fixture(files["picks"])), manifest["latest_started_gw"],
        EntryHistory.model_validate(load_fixture(files["history"])),
        [Transfer.model_validate(t) for t in load_fixture(files["transfers"])],
        {e.id: e for e in data.bootstrap.elements},
    )
    ownership = league_ownership(EntryPicks.model_validate(load_fixture(n)) for n in files["rival_picks"].values())
    return data, state, ownership, datetime.fromisoformat(manifest["fetched_at"])


def money(tenths: int) -> str:
    return f"£{tenths / 10:.1f}m"


def describe(plan: Plan, names: dict[int, str], prices: dict[int, int], sells: dict[int, int], pool: dict[int, PoolPlayer]) -> list[str]:
    sol = plan.solution
    title = "Roll the transfer" if plan.is_roll else ", ".join(
        f"{names[o]} -> {names[i]}" for o, i in paired_transfers(sol.first, pool)
    )
    lines = [f"Plan {plan.rank}: {title}"]
    lines.append(
        f"  xPts gained vs no transfers: {plan.xpts_gain:+.1f}   differential xPts gained: {plan.differential_gain:+.1f}"
        f"   hits: {plan.hits}" + ("" if sol.proven_optimal else "   (best found within the time limit)")
    )
    for gw in sol.gameweeks:
        moves = ", ".join(
            f"{names[o]} ({money(sells.get(o, prices[o]))}) -> {names[i]} ({money(prices[i])})"
            for o, i in paired_transfers(gw, pool)
        ) or "no transfers"
        hit = f", -{4 * gw.hits} hit" if gw.hits else ""
        lines.append(
            f"  GW{gw.gw}: {moves}{hit} | FT {gw.free_transfers}, bank {money(gw.bank)} | "
            f"captain {names[gw.captain]}, vice {names[gw.vice]}"
        )
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--team", type=int, required=True)
    parser.add_argument("--league", type=int, help="Classic league ID (rivals' ownership); omit for points only")
    parser.add_argument("--strategy", choices=list(STRATEGY_WEIGHTS), default="balanced")
    parser.add_argument("--horizon", type=int, default=4, help="Gameweeks to plan over (default 4)")
    parser.add_argument("--max-hits", type=int, default=0, help="Most -4 hits over the whole horizon (default 0)")
    parser.add_argument("--rivals", type=int, default=20, help="Top N rivals by rank (default 20)")
    parser.add_argument("--offline", action="store_true", help="Use saved fixtures (team must match)")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    started = time.perf_counter()
    data, state, ownership, now = load_offline(args.team) if args.offline else load_live(args.team, args.league, args.rivals)
    loaded = time.perf_counter()

    finished = latest_finished_gameweek(data.bootstrap.events)
    actionable = next_actionable_gameweek(data.bootstrap.events, now)
    if actionable is None:
        sys.exit("The season's last deadline has passed.")
    gws = tuple(g for g in range(actionable.id, actionable.id + args.horizon) if g <= 38)
    proj = project(data, train_through=finished.id if finished else 0, target_gws=gws)
    pool = build_pool(data.bootstrap, proj, state, gws)
    plans: PlanSet = make_plans(pool, state, Settings(gws, strategy=args.strategy, max_hits=args.max_hits), ownership)
    done = time.perf_counter()

    names = {e.id: e.web_name for e in data.bootstrap.elements}
    prices = {e.id: e.now_cost for e in data.bootstrap.elements}
    sells = {p.element: p.sell_price for p in state.players}
    started_gw = latest_started_gameweek(data.bootstrap.events, now)
    print(f"Planning GW{gws[0]}-{gws[-1]} | strategy: {args.strategy} | max hits: {args.max_hits} over the next {len(gws)} gameweeks")
    print(f"Squad as of the GW{state.picks_gw} deadline (transfers made since then aren't visible). "
          f"Free transfers: {state.free_transfers}, bank {money(state.bank)}.")
    if ownership.n_rivals:
        print(f"League ownership from {ownership.n_rivals} rivals' GW{started_gw.id if started_gw else '?'} squads (last week's).")
    print()
    for plan in plans.plans:
        print("\n".join(describe(plan, names, prices, sells, {p.element: p for p in pool})))
        print()
    print(f"Loaded data in {loaded - started:.1f}s; projected and solved in {done - loaded:.1f}s.")


if __name__ == "__main__":
    main()
