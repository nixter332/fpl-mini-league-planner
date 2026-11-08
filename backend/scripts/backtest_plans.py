"""Plan backtest: if a manager had followed the planner every week, what would they have scored?

For each manager, start from their real squad after GW (from - 1). Each week from `--from` to
`--to`: project with data from before that deadline only, solve the plan (same as the app's
Plan 1), make its first-week transfers, pick its XI and captain, and score them with the real
points (auto-subs included). Carry squad, bank and free transfers on. Compare with keeping the
starting squad (best XI each week, no transfers) and with what the manager really scored.

Usage (from backend/; uses the cached FPL API, ~150 throttled requests the first time):
    python -m scripts.backtest_plans --leagues 1883627 1863820 1145494 --from 5 --to 10

Limits (see docs/backtest-plans.md): injury news is switched off, because today's news would
leak the future; prices are today's.

Chips: "chips matched" gives the planner the same chip in the same week as the real manager (a
fair comparison of everything but chip timing). "planner chips" lets it play Bench Boost and
Triple Captain itself, and a Wildcard/Free Hit when the best plan with it beats the best plan
without it by CHIP_PLAY_THRESHOLD over the horizon (the app's "chips this week" advice).
"""

import argparse
import json
import sys
import time
from dataclasses import replace
from pathlib import Path

from app.fpl.client import FPLClient
from app.fpl.models import Bootstrap, EntryHistory, EntryPicks, LeagueStandings, Transfer
from app.model.history import SeasonData
from app.model.project import project
from app.optimizer.inputs import build_pool
from app.optimizer.chips import FREE_HIT, WILDCARD, window_for
from app.optimizer.lineup import best_lineup
from app.optimizer.ownership import NO_RIVALS, league_ownership
from app.optimizer.plans import score
from app.optimizer.simulate import advance, score_week
from app.optimizer.solver import Settings, solve
from app.optimizer.state import SquadState, build_state
from scripts.backtest import load_live

HORIZON = 4
CONFIGS = {  # name -> Settings overrides (strategy, ft_value)
    "protect": {"strategy": "protect"},
    "balanced": {"strategy": "balanced"},
    "risky": {"strategy": "risky"},
    "protect, saved FT worth 0": {"strategy": "protect", "ft_value": 0.0},
    "protect, no hits": {"strategy": "protect", "max_hits": 0},
    "balanced, no hits": {"strategy": "balanced", "max_hits": 0},
    "protect, no hits, saved FT worth 0": {"strategy": "protect", "max_hits": 0, "ft_value": 0.0},
    "protect, no hits, chips matched": {"strategy": "protect", "max_hits": 0, "chips": "matched"},
    "balanced, no hits, chips matched": {"strategy": "balanced", "max_hits": 0, "chips": "matched"},
    "protect, no hits, planner chips": {"strategy": "protect", "max_hits": 0, "chips": "planner"},
}
# Play a Wildcard / Free Hit when it beats the best plan without it by this many xPts over the horizon.
CHIP_PLAY_THRESHOLD = {WILDCARD: 6.0, FREE_HIT: 4.0}


def truncated_history(history: EntryHistory, through: int) -> EntryHistory:
    return EntryHistory(
        current=[r for r in history.current if r.event <= through],
        chips=[c for c in history.chips if c.event <= through],
    )


def start_state(entry: int, gw_before: int, picks: dict[int, EntryPicks], history: EntryHistory,
                transfers: list[Transfer], elements, bootstrap: Bootstrap) -> SquadState:
    """The real squad going into GW gw_before + 1 (a free hit reverts, so use the week before)."""
    gw = gw_before
    if picks[gw].active_chip == "freehit" and gw > 1:
        gw -= 1
    rules = bootstrap.game_config.rules
    state = build_state(entry, picks[gw], gw, truncated_history(history, gw_before),
                        [t for t in transfers if t.event <= gw_before], elements,
                        rules.transfers_sell_on_fee, rules.max_extra_free_transfers + 1, bootstrap.chips)
    return replace(state, bank=picks[gw_before].entry_history.bank)


def plan_one(pool, state, settings, ownership):
    """The app's Plan 1: the best plan under the strategy, never worse than no transfers."""
    players = {p.element: p for p in pool}
    baseline = solve(pool, state, replace(settings, strategy="protect").without_chips(), ownership, no_transfers=True)
    floor, _ = score(baseline, players, ownership, settings)
    best = solve(pool, state, settings, ownership, warm_start=baseline, min_xpts=floor)
    return best or baseline


def choose(pool, state, settings: Settings, ownership, chip_mode: str | None, real_chip: str | None, gw: int):
    """This week's plan under a chip mode (see the module docstring)."""
    players = {p.element: p for p in pool}
    if chip_mode is None:
        return plan_one(pool, state, settings, ownership)
    settings = replace(settings, chips=state.chips)
    if chip_mode == "matched":
        forced = ((gw, real_chip),) if real_chip and window_for(state.chips, real_chip, gw) else ()
        return plan_one(pool, state, replace(settings, auto_chips=frozenset(), forced_chips=forced), ownership)
    best = plan_one(pool, state, settings, ownership)
    best_x = score(best, players, ownership, settings)[0]
    for chip in (WILDCARD, FREE_HIT):
        if window_for(state.chips, chip, gw) is None:
            continue
        alt = plan_one(pool, state, replace(settings, forced_chips=((gw, chip),)), ownership)
        alt_x = score(alt, players, ownership, settings)[0]
        if alt_x - best_x >= CHIP_PLAY_THRESHOLD[chip]:
            best, best_x = alt, alt_x - CHIP_PLAY_THRESHOLD[chip]  # the next chip must beat this by its own margin
    return best


def report(path: Path) -> str:
    """Markdown tables from a saved run."""
    run = json.loads(path.read_text(encoding="utf-8"))
    gws = [str(g) for g in run["gws"]]
    rows = run["results"]
    configs = list(rows[0]["sims"])
    n = len(rows)

    def total(pts: dict) -> int:
        return sum(pts.get(g, 0) for g in gws)

    real = [total(r["actual"]) for r in rows]
    hold = [total(r["sims"]["no transfers"]["points"]) for r in rows]
    out = [f"GW{gws[0]}–GW{gws[-1]}, {n} managers. Points are net of hits.", ""]
    out += ["| Way of playing | Avg points | vs real manager | vs no transfers | Beat the real manager | Hits taken |",
            "| --- | --- | --- | --- | --- | --- |",
            f"| What managers really did | {sum(real) / n:.1f} | | {(sum(real) - sum(hold)) / n:+.1f} | | |"]
    for c in configs:
        pts = [total(r["sims"][c]["points"]) for r in rows]
        beat = sum(p > a for p, a in zip(pts, real))
        hits = sum(sum(r["sims"][c]["hits"].values()) for r in rows)
        out.append(f"| {c} | {sum(pts) / n:.1f} | {(sum(pts) - sum(real)) / n:+.1f} | {(sum(pts) - sum(hold)) / n:+.1f} | {beat} of {n} | {hits} |")

    out += ["", "| Manager | Chips used | Real | " + " | ".join(configs) + " |",
            "| --- | --- | --- | " + " | ".join("---" for _ in configs) + " |"]
    for r in rows:
        chips = ", ".join(f"{v} GW{k}" for k, v in sorted(r["chips"].items())) or "—"
        out.append(f"| {r['name']} | {chips} | {total(r['actual'])} | " + " | ".join(str(total(r["sims"][c]["points"])) for c in configs) + " |")

    out += ["", "| GW | Real (avg) | " + " | ".join(configs) + " |",
            "| --- | --- | " + " | ".join("---" for _ in configs) + " |"]
    for g in gws:
        cells = [f"{sum(r['sims'][c]['points'].get(g, 0) for r in rows) / n:.1f}" for c in configs]
        out.append(f"| {g} | {sum(r['actual'].get(g, 0) for r in rows) / n:.1f} | " + " | ".join(cells) + " |")
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--leagues", type=int, nargs="+", default=[], help="every member of each league is simulated; rivals = the other members")
    ap.add_argument("--from", dest="start", type=int, default=5)
    ap.add_argument("--to", dest="end", type=int, default=None)
    ap.add_argument("--max-hits", type=int, default=1)
    ap.add_argument("--configs", nargs="+", default=None, help=f"subset of: {', '.join(CONFIGS)}")
    ap.add_argument("--out", type=Path, default=Path("data/cache/backtest-plans.json"))
    ap.add_argument("--report", action="store_true", help="only print the tables for a saved run (--out)")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if args.report:
        print(report(args.out))
        return
    if not args.leagues:
        ap.error("--leagues is required unless --report")

    configs = {k: CONFIGS[k] for k in (args.configs or CONFIGS)}
    data: SeasonData = load_live()
    bootstrap = data.bootstrap
    end = args.end or max(data.live)
    gws = list(range(args.start, end + 1))
    elements = {e.id: e for e in bootstrap.elements}
    position = {e.id: e.element_type for e in bootstrap.elements}
    live = {gw: {el.id: el.stats for el in data.live[gw].elements} for gw in gws}
    exists = {gw: {el.id for el in data.live[gw].elements} for gw in gws}  # players in the game that week

    # ---- managers, their leagues, picks and histories (cached after the first run) ----------
    t0 = time.perf_counter()
    groups: dict[int, list[int]] = {}
    names: dict[int, str] = {}
    seen: set[int] = set()
    with FPLClient() as client:
        for league in args.leagues:
            rows = LeagueStandings.model_validate(client.league_standings(league)).standings.results
            groups[league] = [r.entry for r in rows]
            names.update({r.entry: r.player_name for r in rows})
        everyone = sorted({m for g in groups.values() for m in g})
        picks: dict[int, dict[int, EntryPicks]] = {m: {} for m in everyone}
        for gw in range(max(1, args.start - 2), end):  # squads before each simulated week
            for m, raw in client.many_entry_picks(everyone, gw).items():
                if raw is not None:
                    picks[m][gw] = EntryPicks.model_validate(raw)
        histories = {m: EntryHistory.model_validate(client.entry_history(m)) for m in everyone}
        transfers = {m: [Transfer.model_validate(t) for t in client.entry_transfers(m)] for m in everyone}
    print(f"Loaded {len(everyone)} managers in {time.perf_counter() - t0:.0f}s", flush=True)

    # Each manager is simulated once, in the first (smallest) league they're in.
    subjects = []
    for league, members in groups.items():
        for m in members:
            if m not in seen and args.start - 1 in picks[m]:
                subjects.append((league, m))
                seen.add(m)

    projections = {}
    for gw in gws:
        targets = tuple(g for g in range(gw, gw + HORIZON) if g <= len(bootstrap.events))
        projections[gw] = project(data, train_through=gw - 1, target_gws=targets, use_availability=False)
    xpts = {gw: {int(e): float(v) for (e, g), v in projections[gw]["xpts"].items() if g == gw} for gw in gws}

    results = []
    for league, m in subjects:
        t1 = time.perf_counter()
        rivals = [r for r in groups[league] if r != m]
        actual = {r.event: r.points - r.event_transfers_cost for r in histories[m].current if r.event in gws}
        chips = {c.event: c.name for c in histories[m].chips if c.event in gws}
        first = start_state(m, args.start - 1, picks[m], histories[m], transfers[m], elements, bootstrap)

        row = {"league": league, "entry": m, "name": names[m], "actual": actual, "chips": chips, "sims": {}}
        # Hold: keep the starting squad, best XI and captain by the model each week.
        hold = {}
        for gw in gws:
            lu = best_lineup(first.element_ids, position, xpts[gw])
            stats = live[gw]
            hold[gw] = score_week(lu.starting, lu.bench, lu.captain, lu.vice, position,
                                  {e: s.minutes for e, s in stats.items()}, {e: s.total_points for e, s in stats.items()}).points
        row["sims"]["no transfers"] = {"points": hold, "hits": {}, "moves": {}}

        for name, overrides in configs.items():
            opts = dict(overrides)
            chip_mode = opts.pop("chips", None)
            state = first
            pts, hits, moves, played = {}, {}, {}, {}
            for gw in gws:
                targets = tuple(g for g in range(gw, gw + HORIZON) if g <= len(bootstrap.events))
                ownership = league_ownership(picks[r][gw - 1] for r in rivals if gw - 1 in picks[r]) if rivals else NO_RIVALS
                pool = build_pool(bootstrap, projections[gw], state, targets, available=exists[gw])
                settings = Settings(targets, **{"max_hits": args.max_hits, "time_limit": 3.0, **opts})
                sol = choose(pool, state, settings, ownership, chip_mode, chips.get(gw), gw).first
                stats = live[gw]
                week = score_week(sol.starting, sol.bench, sol.captain, sol.vice, position,
                                  {e: s.minutes for e, s in stats.items()}, {e: s.total_points for e, s in stats.items()},
                                  chip=sol.chip)
                if sol.chip:
                    played[gw] = sol.chip
                pts[gw] = week.points - 4 * sol.hits
                hits[gw] = sol.hits
                moves[gw] = [[o, i] for o, i in zip(sol.transfers_out, sol.transfers_in)]
                state = advance(state, sol, {p.element: p for p in pool})
            row["sims"][name] = {"points": pts, "hits": hits, "moves": moves, "chips": played}
        results.append(row)
        sims = "  ".join(f"{k}: {sum(v['points'].values())}" for k, v in row["sims"].items())
        print(f"{names[m][:22]:<22} actual: {sum(actual.values())}  {sims}  ({time.perf_counter() - t1:.0f}s)", flush=True)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"gws": gws, "results": results, "names": {e.id: e.web_name for e in bootstrap.elements}}, indent=1), encoding="utf-8")
    print(f"\nSaved {args.out}")


if __name__ == "__main__":
    main()
