"""Tune the planner's settings on the collected manager sample (parallel, resumable).

Each config is a variation of BASE. Every manager in data/cache/manager-sample/ is simulated
from their real squad after GW(from-1): each week the planner plans with data from before that
deadline, plays its first-week moves (and chips, by the config's chip mode), and is scored with
real points and FPL auto-subs. Results go to data/cache/tune/{config}.jsonl, one manager per line,
so a rerun only does what's missing.

Fair chip scoring: a first-half chip still unused at the end is credited at an estimated value,
for the planner and the real manager alike (see chip_credit), so holding chips isn't a loss.

Usage (from backend/):
    python -m scripts.tune --from 4 --to 9 --workers 14            # all configs
    python -m scripts.tune --configs base "WC bar 15" --workers 14
    python -m scripts.tune --report                                # tables from saved runs
"""

import argparse
import json
import math
import os
import re
import statistics as st
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import replace
from pathlib import Path
from typing import Any

from app.fpl.client import FPLClient
from app.fpl.models import EntryHistory, EntryPicks, LeagueStandings, Transfer
from app.model.project import project
from app.optimizer.chips import BENCH_BOOST, FREE_HIT, TRIPLE_CAPTAIN, WILDCARD, chips_left, window_for
from app.optimizer.inputs import build_pool
from app.optimizer.lineup import best_lineup
from app.optimizer.ownership import NO_RIVALS, league_ownership
from app.optimizer.plans import score
from app.optimizer.simulate import advance, score_week
from app.optimizer.solver import Settings
from scripts.backtest import load_live
from scripts.backtest_plans import plan_one, start_state
from scripts.collect_managers import LEAGUES

SAMPLE = Path("data/cache/manager-sample")
OUT = Path("data/cache/tune")
HORIZON = 4
FIRST_HALF_END = 19

# The app's settings today: Protect, no hits, saved FT 1.5, BB/TC keep 8/6, planner plays chips;
# Wildcard/Free Hit when the best plan with it beats the best without by these xPts.
BASE: dict[str, Any] = {"strategy": "protect", "max_hits": 0, "chips": "planner", "wc_bar": 10.0, "fh_bar": 4.0}
CONFIGS: dict[str, dict[str, Any]] = {
    "base": {},
    "no chips": {"chips": None},
    "chips matched to the real manager": {"chips": "matched"},
    "WC bar 15": {"wc_bar": 15.0},
    "WC never": {"wc_bar": None},
    "FH never": {"fh_bar": None},
    "BB/TC keep low (4/3)": {"chip_keep": ((BENCH_BOOST, 4.0), (TRIPLE_CAPTAIN, 3.0))},
    "BB/TC keep high (12/9)": {"chip_keep": ((BENCH_BOOST, 12.0), (TRIPLE_CAPTAIN, 9.0))},
    "saved FT worth 0": {"ft_value": 0.0},
    "saved FT worth 3": {"ft_value": 3.0},
    "1 hit allowed": {"max_hits": 1},
    "1 hit, margin 2": {"max_hits": 1, "hit_margin": 2.0},
    "2 hits, margin 4": {"max_hits": 2, "hit_margin": 4.0},
}
# Estimated value of a first-half chip still unused at the end (it can still be played by GW19).
# Bench Boost and Triple Captain are measured from the sample's real chip weeks; Wildcard and
# Free Hit are assumptions (their value can't be read off one week's points: measuring a Free
# Hit as "that week minus the manager's average" came out negative on the sample).
WILDCARD_CREDIT = 10.0
FREE_HIT_CREDIT = 6.0

_W: dict[str, Any] = {}  # per-worker globals


def result_path(name: str) -> Path:
    """Where a config's results go. Names like "BB/TC keep low (4/3)" must not become folders."""
    return OUT / (re.sub(r"[^\w .,()-]+", "-", name) + ".jsonl")


def _init(data, projections, exists, start: int, end: int, league_picks) -> None:
    _W.update(
        data=data, projections=projections, exists=exists, start=start, end=end, league_picks=league_picks,
        elements={e.id: e for e in data.bootstrap.elements},
        position={e.id: e.element_type for e in data.bootstrap.elements},
        live={gw: {el.id: el.stats for el in data.live[gw].elements} for gw in range(start, end + 1)},
    )


def _choose(pool, state, settings: Settings, ownership, cfg: dict, real_chip: str | None, gw: int):
    players = {p.element: p for p in pool}
    mode = cfg["chips"]
    if mode is None:
        return plan_one(pool, state, settings.without_chips(), ownership)
    settings = replace(settings, chips=state.chips)
    if mode == "matched":
        forced = ((gw, real_chip),) if real_chip and window_for(state.chips, real_chip, gw) else ()
        return plan_one(pool, state, replace(settings, auto_chips=frozenset(), forced_chips=forced), ownership)
    best = plan_one(pool, state, settings, ownership)
    best_x = score(best, players, ownership, settings)[0]
    for chip, bar in ((WILDCARD, cfg["wc_bar"]), (FREE_HIT, cfg["fh_bar"])):
        if bar is None or window_for(state.chips, chip, gw) is None:
            continue
        alt = plan_one(pool, state, replace(settings, forced_chips=((gw, chip),)), ownership)
        alt_x = score(alt, players, ownership, settings)[0]
        if alt_x - best_x >= bar:
            best, best_x = alt, alt_x - bar
    return best


def simulate(manager: dict, name: str, cfg: dict) -> dict:
    W = _W
    start, end = W["start"], W["end"]
    gws = list(range(start, end + 1))
    picks = {int(g): EntryPicks.model_validate(v) for g, v in manager["picks"].items()}
    history = EntryHistory.model_validate(manager["history"])
    transfers = [Transfer.model_validate(t) for t in manager["transfers"]]
    first = start_state(manager["entry"], start - 1, picks, history, transfers, W["elements"], W["data"].bootstrap)
    real_chips = {c.event: c.name for c in history.chips}
    rivals = {}
    if manager["league"]:
        rivals = {e: p for e, p in W["league_picks"][manager["league"]].items() if e != manager["entry"]}

    settings_kw = {k: v for k, v in cfg.items() if k not in ("chips", "wc_bar", "fh_bar")}
    state, pts, played, hits = first, {}, {}, 0
    for gw in gws:
        targets = tuple(g for g in range(gw, gw + HORIZON) if g <= len(W["data"].bootstrap.events))
        ownership = (
            league_ownership(EntryPicks.model_validate(p[str(gw - 1)]) for p in rivals.values() if str(gw - 1) in p)
            if rivals else NO_RIVALS
        )
        pool = build_pool(W["data"].bootstrap, W["projections"][gw], state, targets, available=W["exists"][gw])
        settings = Settings(targets, time_limit=2.0, **settings_kw)
        sol = _choose(pool, state, settings, ownership, cfg, real_chips.get(gw), gw).first
        stats = W["live"][gw]
        week = score_week(sol.starting, sol.bench, sol.captain, sol.vice, W["position"],
                          {e: s.minutes for e, s in stats.items()}, {e: s.total_points for e, s in stats.items()}, chip=sol.chip)
        pts[gw] = week.points - 4 * sol.hits
        hits += sol.hits
        if sol.chip:
            played[gw] = sol.chip
        state = advance(state, sol, {p.element: p for p in pool})

    real_left = chips_left(W["data"].bootstrap.chips, [c for c in history.chips if c.event <= end], end + 1)
    hold = {}
    for gw in gws:
        lu = best_lineup(first.element_ids, W["position"], {int(e): float(v) for (e, g), v in W["projections"][gw]["xpts"].items() if g == gw})
        stats = W["live"][gw]
        hold[gw] = score_week(lu.starting, lu.bench, lu.captain, lu.vice, W["position"],
                              {e: s.minutes for e, s in stats.items()}, {e: s.total_points for e, s in stats.items()}).points
    real = {r.event: r.points - r.event_transfers_cost for r in history.current if start <= r.event <= end}
    return {
        "entry": manager["entry"], "band": manager["band"], "group": manager["group"],
        "sim": pts, "real": real, "hold": hold, "hits": hits, "chips": played,
        "sim_unused": sorted(c.name for c in state.chips if c.stop <= FIRST_HALF_END),
        "real_unused": sorted(c.name for c in real_left if c.stop <= FIRST_HALF_END),
    }


def _task(manager: dict, name: str, cfg: dict) -> tuple[str, dict | None, str | None]:
    try:
        return name, simulate(manager, name, cfg), None
    except Exception as e:  # report and carry on
        return name, None, f"{manager['entry']}: {type(e).__name__}: {e}"


def load_sample() -> list[dict]:
    return [json.loads(f.read_text(encoding="utf-8")) for f in sorted(SAMPLE.glob("*.json")) if not f.name.startswith("_")]


def chip_credit(sample: list[dict], start: int, end: int, live: dict) -> dict[str, float]:
    """What a first-half chip is worth when played, measured on the sample's real chip weeks:
    Bench Boost = bench points, Triple Captain = captain points. Wildcard and Free Hit are
    assumptions (WILDCARD_CREDIT, FREE_HIT_CREDIT)."""
    bb, tc = [], []
    for m in sample:
        history = EntryHistory.model_validate(m["history"])
        for c in history.chips:
            raw = m["picks"].get(str(c.event))
            if not raw or c.event not in live:
                continue
            pk = EntryPicks.model_validate(raw)
            pts = {e: s.total_points for e, s in live[c.event].items()}
            if c.name == BENCH_BOOST:
                bb.append(sum(pts.get(p.element, 0) for p in pk.picks if p.position > 11))
            elif c.name == TRIPLE_CAPTAIN:
                tc.append(pts.get(next(p.element for p in pk.picks if p.is_captain), 0))
    mean = lambda xs, d: st.mean(xs) if xs else d
    return {BENCH_BOOST: mean(bb, 8.0), TRIPLE_CAPTAIN: mean(tc, 6.0), FREE_HIT: FREE_HIT_CREDIT, WILDCARD: WILDCARD_CREDIT}


def run(names: list[str], start: int, end: int, workers: int) -> None:
    sample = load_sample()
    data = load_live()
    print(f"{len(sample)} managers; GW{start}-GW{end}; configs: {', '.join(names)}", flush=True)
    projections = {}
    for gw in range(start, end + 1):
        targets = tuple(g for g in range(gw, gw + HORIZON) if g <= len(data.bootstrap.events))
        projections[gw] = project(data, train_through=gw - 1, target_gws=targets, use_availability=False)
    exists = {gw: frozenset(el.id for el in data.live[gw].elements) for gw in range(start, end + 1)}
    # Rivals: every member of each league (someone in several leagues is in the sample once).
    by_entry = {m["entry"]: m for m in sample}
    league_picks: dict[int, dict[int, dict]] = {}
    with FPLClient() as client:
        for league_id in LEAGUES:
            rows = LeagueStandings.model_validate(client.league_standings(league_id)).standings.results
            league_picks[league_id] = {r.entry: by_entry[r.entry]["picks"] for r in rows if r.entry in by_entry}

    OUT.mkdir(parents=True, exist_ok=True)
    tasks = []
    for name in names:
        path = result_path(name)
        done = set()
        if path.exists():
            done = {json.loads(line)["entry"] for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}
        cfg = {**BASE, **CONFIGS[name]}
        tasks += [(m, name, cfg) for m in sample if m["entry"] not in done and str(start - 1) in m["picks"]]
    print(f"{len(tasks)} simulations to run", flush=True)
    started = time.perf_counter()
    with ProcessPoolExecutor(max_workers=workers, initializer=_init, initargs=(data, projections, exists, start, end, league_picks)) as pool:
        futures = [pool.submit(_task, *t) for t in tasks]
        for i, fut in enumerate(as_completed(futures), 1):
            name, result, error = fut.result()
            if error:
                print(f"  [{name}] failed {error}", flush=True)
            else:
                try:
                    with open(result_path(name), "a", encoding="utf-8") as f:
                        f.write(json.dumps(result) + "\n")
                except OSError as e:  # never let one bad write end the run
                    print(f"  [{name}] couldn't save {result['entry']}: {e}", flush=True)
            if i % 50 == 0 or i == len(futures):
                print(f"  {i}/{len(futures)} ({(time.perf_counter() - started) / 60:.0f} min)", flush=True)


def report(start: int, end: int) -> str:
    sample = load_sample()
    data = load_live()
    live = {gw: {el.id: el.stats for el in data.live[gw].elements} for gw in data.live}
    credit = chip_credit(sample, 1, end, live)
    lines = [
        f"GW{start}-GW{end}. Totals over the window, net of hits. Unused first-half chips at the end are credited at "
        + ", ".join(f"{k} {v:.1f}" for k, v in credit.items()) + " (planner and real manager alike).",
        "",
        "| Config | Managers | vs real (all) | ±95% | vs real: leagues | rank ~1M-10k | rank ~1k | India top 200 | Half A | Half B | vs no transfers | Hits/manager | Chips played |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for name in CONFIGS:
        path = result_path(name)
        if not path.exists():
            continue
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if not rows:
            continue

        def total(r: dict, key: str) -> float:
            return sum(r[key].get(str(g), r[key].get(g, 0)) for g in range(start, end + 1))

        def diff(r: dict) -> float:
            sim = total(r, "sim") + sum(credit[c] for c in r["sim_unused"])
            real = total(r, "real") + sum(credit[c] for c in r["real_unused"])
            return sim - real

        def m(rs: list[dict]) -> str:
            return f"{st.mean(diff(r) for r in rs):+.1f}" if rs else "—"

        d = [diff(r) for r in rows]
        ci = 2 * st.stdev(d) / math.sqrt(len(d)) if len(d) > 1 else float("nan")
        groups = {
            "leagues": [r for r in rows if r["group"] == "leagues"],
            "mid": [r for r in rows if r["band"] in ("rank ~1M", "rank ~100k", "rank ~10k")],
            "1k": [r for r in rows if r["band"] == "rank ~1k"],
            "india": [r for r in rows if r["band"] == "India top 200"],
        }
        vs_hold = st.mean(total(r, "sim") - total(r, "hold") for r in rows)
        chips: dict[str, int] = {}
        for r in rows:
            for c in r["chips"].values():
                chips[c] = chips.get(c, 0) + 1
        chip_txt = ", ".join(f"{k} {v / len(rows):.0%}" for k, v in sorted(chips.items())) or "none"
        lines.append(
            f"| {name} | {len(rows)} | {st.mean(d):+.1f} | {ci:.1f} | {m(groups['leagues'])} | {m(groups['mid'])} | {m(groups['1k'])} | "
            f"{m(groups['india'])} | {m([r for r in rows if r['entry'] % 2 == 0])} | {m([r for r in rows if r['entry'] % 2 == 1])} | "
            f"{vs_hold:+.1f} | {st.mean(r['hits'] for r in rows):.1f} | {chip_txt} |"
        )
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from", dest="start", type=int, default=4)
    ap.add_argument("--to", dest="end", type=int, default=9)
    ap.add_argument("--configs", nargs="+", default=None, help=f"subset of: {', '.join(CONFIGS)}")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if args.report:
        print(report(args.start, args.end))
        return
    run(args.configs or list(CONFIGS), args.start, args.end, args.workers)
    print()
    print(report(args.start, args.end))


if __name__ == "__main__":
    main()
