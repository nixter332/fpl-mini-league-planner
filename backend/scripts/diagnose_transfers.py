"""Why do the planner's transfers add so little? Projected vs actual gain, transfer by transfer.

Re-simulates the "no chips" setting (Protect, no hits) on a slice of the collected sample,
recording every transfer it makes: what it was projected to gain over the weeks it's held in
the window, and what it actually gained (real points, in minus out, same weeks). Then splits
the gap into: players bought who then didn't play (injury news would have caught many),
projection bias on players bought vs sold, and plain luck.

Usage (from backend/):  python -m scripts.diagnose_transfers --every 3 --workers 3
"""

import argparse
import json
import statistics as st
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from app.fpl.models import EntryHistory, EntryPicks, Transfer
from app.model.project import project
from app.optimizer.inputs import build_pool
from app.optimizer.ownership import NO_RIVALS
from app.optimizer.simulate import advance
from app.optimizer.solver import Settings
from scripts.backtest import load_live
from scripts.backtest_plans import plan_one, start_state
from scripts.tune import load_sample

HORIZON = 4
_W: dict = {}


def _init(data, projections, exists, start, end):
    _W.update(data=data, projections=projections, exists=exists, start=start, end=end,
              elements={e.id: e for e in data.bootstrap.elements},
              live={gw: {el.id: el.stats for el in data.live[gw].elements} for gw in data.live})


def transfers_for(manager: dict) -> list[dict]:
    W = _W
    start, end = W["start"], W["end"]
    picks = {int(g): EntryPicks.model_validate(v) for g, v in manager["picks"].items()}
    history = EntryHistory.model_validate(manager["history"])
    transfers = [Transfer.model_validate(t) for t in manager["transfers"]]
    state = start_state(manager["entry"], start - 1, picks, history, transfers, W["elements"], W["data"].bootstrap)
    out = []
    for gw in range(start, end + 1):
        targets = tuple(g for g in range(gw, gw + HORIZON) if g <= len(W["data"].bootstrap.events))
        pool = build_pool(W["data"].bootstrap, W["projections"][gw], state, targets, available=W["exists"][gw])
        sol = plan_one(pool, state, Settings(targets, strategy="protect", max_hits=0, time_limit=2.0), NO_RIVALS).first
        held = [g for g in targets if g <= end]  # weeks we can score
        players = {p.element: p for p in pool}
        for o, i in zip(sol.transfers_out, sol.transfers_in):
            act = lambda p, g: W["live"][g].get(p).total_points if W["live"][g].get(p) else 0
            mins = lambda p, g: W["live"][g].get(p).minutes if W["live"][g].get(p) else 0
            out.append({
                "entry": manager["entry"], "band": manager["band"], "gw": gw, "out": o, "in": i,
                "proj_in": sum(players[i].xpts.get(g, 0.0) for g in held),
                "proj_out": sum(players[o].xpts.get(g, 0.0) for g in held),
                "act_in": sum(act(i, g) for g in held), "act_out": sum(act(o, g) for g in held),
                "in_played_first_week": mins(i, gw) > 0, "out_played_first_week": mins(o, gw) > 0,
                "weeks": len(held),
            })
        state = advance(state, sol, players)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from", dest="start", type=int, default=4)
    ap.add_argument("--to", dest="end", type=int, default=9)
    ap.add_argument("--every", type=int, default=3, help="use every Nth manager")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--out", type=Path, default=Path("data/cache/diagnose-transfers.json"))
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    if not args.out.exists():
        data = load_live()
        sample = [m for k, m in enumerate(load_sample()) if k % args.every == 0 and str(args.start - 1) in m["picks"]]
        projections = {gw: project(data, train_through=gw - 1, target_gws=tuple(range(gw, gw + HORIZON)), use_availability=False)
                       for gw in range(args.start, args.end + 1)}
        exists = {gw: frozenset(el.id for el in data.live[gw].elements) for gw in range(args.start, args.end + 1)}
        rows = []
        with ProcessPoolExecutor(args.workers, initializer=_init, initargs=(data, projections, exists, args.start, args.end)) as pool:
            for result in pool.map(_safe, sample):
                rows += result
        args.out.write_text(json.dumps(rows), encoding="utf-8")
    rows = json.loads(args.out.read_text(encoding="utf-8"))
    print(report(rows))


def _safe(m):
    try:
        return transfers_for(m)
    except Exception:
        return []


def report(rows: list[dict]) -> str:
    n = len(rows)
    mean = lambda xs: st.mean(xs) if xs else float("nan")
    proj = [r["proj_in"] - r["proj_out"] for r in rows]
    act = [r["act_in"] - r["act_out"] for r in rows]
    lines = [f"{n} transfers by the planner (Protect, no hits, no chips), GW4-9, weeks held within the window.", ""]
    lines.append(f"- Projected gain per transfer: {mean(proj):+.2f}   actual: {mean(act):+.2f}   shortfall: {mean(proj) - mean(act):.2f}")
    lines.append(f"- Players bought: projected {mean([r['proj_in'] for r in rows]):.2f}, scored {mean([r['act_in'] for r in rows]):.2f} "
                 f"(bias {mean([r['proj_in'] - r['act_in'] for r in rows]):+.2f})")
    lines.append(f"- Players sold:   projected {mean([r['proj_out'] for r in rows]):.2f}, scored {mean([r['act_out'] for r in rows]):.2f} "
                 f"(bias {mean([r['proj_out'] - r['act_out'] for r in rows]):+.2f})")
    dnp = [r for r in rows if not r["in_played_first_week"]]
    lines.append(f"- Bought a player who didn't play the next week: {len(dnp)} of {n} ({len(dnp) / max(1, n):.0%}); "
                 f"their transfers' actual gain {mean([r['act_in'] - r['act_out'] for r in dnp]):+.2f} vs projected {mean([r['proj_in'] - r['proj_out'] for r in dnp]):+.2f}")
    played = [r for r in rows if r["in_played_first_week"]]
    lines.append(f"- Transfers where the new player did play: projected {mean([r['proj_in'] - r['proj_out'] for r in played]):+.2f}, "
                 f"actual {mean([r['act_in'] - r['act_out'] for r in played]):+.2f}")
    sold_benched = [r for r in rows if not r["out_played_first_week"]]
    lines.append(f"- Sold a player who wasn't playing anyway: {len(sold_benched)} of {n} ({len(sold_benched) / max(1, n):.0%})")
    small = [r for r in rows if r["proj_in"] - r["proj_out"] < 2]
    big = [r for r in rows if r["proj_in"] - r["proj_out"] >= 4]
    lines.append(f"- Small projected gains (<2): {len(small)} transfers, actual {mean([r['act_in'] - r['act_out'] for r in small]):+.2f}; "
                 f"big (4+): {len(big)}, projected {mean([r['proj_in'] - r['proj_out'] for r in big]):+.2f}, actual {mean([r['act_in'] - r['act_out'] for r in big]):+.2f}")
    by_gw = {}
    for r in rows:
        by_gw.setdefault(r["gw"], []).append(r)
    lines.append("- By gameweek (projected vs actual gain per transfer): " + ", ".join(
        f"GW{g} {mean([r['proj_in'] - r['proj_out'] for r in rs]):+.1f}/{mean([r['act_in'] - r['act_out'] for r in rs]):+.1f} ({len(rs)})"
        for g, rs in sorted(by_gw.items())))
    return "\n".join(lines)


if __name__ == "__main__":
    main()
