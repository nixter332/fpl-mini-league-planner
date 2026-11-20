"""Backtest the chip planner's timing (phase 7 gate): does "play it in the best projected week"
pick better weeks than chance, and better than the weeks real managers chose?

For every manager in data/cache/manager-sample/ and each of Bench Boost, Triple Captain and
Free Hit, over a window of gameweeks (default GW5-10):

1. **Planner.** Before each deadline g, using only data from before it (projections trained on
   GW < g, the manager's real squad after GW g-1, no injury news), score every remaining week of
   the window with the chip planner (app/optimizer/chipplan.py). Play the chip in g if g is the
   best of them ("best" rule), or if g is within CLOSE of the best ("early" rule). The window's
   last week plays it regardless, so the planner always uses the chip.
2. **Real points.** What the chip actually added in the chosen week:
   - Bench Boost: the manager's real bench that week (their own lineup, FPL auto-subs).
   - Triple Captain: their real captain's points once more.
   - Free Hit: the planner's one-week squad against the manager's own squad, both with the
     model's lineup and captain, scored with real points and auto-subs.
3. **Compared with:**
   - an average week of the window (playing it at random),
   - the best week in hindsight (the ceiling),
   - chip-matched: for managers who really played the chip in the window, the week they chose,
     scored the same way.

Weeks in which the manager really played a different chip are skipped (one chip per week).
The Free Hit's projected gain is recorded next to its real gain, which measures how much the
planner overrates a Free Hit squad (it sets FREE_HIT_BUY_DISCOUNT).

Limits: the window ends at GW10, not GW19, so the planner must play within 6 weeks while real
managers could wait; there were no blank or double gameweeks; prices are today's.

Usage (from backend/):
    python -m scripts.backtest_chips --from 5 --to 10 --workers 4
    python -m scripts.backtest_chips --report
"""

import argparse
import json
import math
import os
import statistics as st
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import replace
from pathlib import Path
from typing import Any

from app.fpl.models import EntryHistory, EntryPicks, Transfer
from app.model.project import project
from app.optimizer.chipplan import CLOSE, bench_boost_week, free_hit_week, triple_captain_week
from app.optimizer.chips import BENCH_BOOST, CHIP_LABELS, FREE_HIT, TRIPLE_CAPTAIN, ChipWindow
from app.optimizer.inputs import build_pool
from app.optimizer.lineup import best_lineup
from app.optimizer.simulate import score_week
from scripts.backtest import load_live
from scripts.backtest_plans import start_state

SAMPLE = Path("data/cache/manager-sample")
OUT = Path("data/cache/backtest-chip-planner.jsonl")
CHIPS = (BENCH_BOOST, TRIPLE_CAPTAIN, FREE_HIT)

_W: dict[str, Any] = {}


def _init(data, projections, exists, start, end) -> None:
    _W.update(
        data=data, projections=projections, exists=exists, start=start, end=end,
        elements={e.id: e for e in data.bootstrap.elements},
        position={e.id: e.element_type for e in data.bootstrap.elements},
        live={gw: {el.id: el.stats for el in data.live[gw].elements} for gw in range(start, end + 1)},
    )


def _xpts(gw_decided: int, gw: int) -> dict[int, float]:
    """Projections made before gw_decided's deadline, for gw."""
    proj = _W["projections"][gw_decided]
    return {int(e): float(v) for (e, g), v in proj["xpts"].items() if g == gw}


def _score(starting, bench, captain, vice, gw: int, chip: str | None = None) -> int:
    stats = _W["live"][gw]
    return score_week(starting, bench, captain, vice, _W["position"],
                      {e: s.minutes for e, s in stats.items()}, {e: s.total_points for e, s in stats.items()}, chip=chip).points


def _real_lineup(pk: EntryPicks):
    ordered = sorted(pk.picks, key=lambda p: p.position)
    starting = [p.element for p in ordered if p.position <= 11]
    bench = [p.element for p in ordered if p.position > 11]
    captain = next(p.element for p in ordered if p.is_captain)
    vice = next((p.element for p in ordered if p.is_vice_captain), captain)
    return starting, bench, captain, vice


def _model_score(squad, gw: int, xpts: dict[int, float]) -> int:
    lu = best_lineup(squad, _W["position"], xpts)
    return _score(lu.starting, lu.bench, lu.captain, lu.vice, gw)


def simulate(manager: dict) -> dict:
    start, end = _W["start"], _W["end"]
    picks = {int(g): EntryPicks.model_validate(v) for g, v in manager["picks"].items()}
    history = EntryHistory.model_validate(manager["history"])
    transfers = [Transfer.model_validate(t) for t in manager["transfers"]]
    real_chips = {c.event: c.name for c in history.chips}
    states, fh_cache = {}, {}

    def state(g: int):  # the squad going into g, as known before g's deadline
        if g not in states:
            states[g] = start_state(manager["entry"], g - 1, picks, history, transfers, _W["elements"], _W["data"].bootstrap)
        return states[g]

    def free_hit(decided: int, g: int) -> tuple[float, tuple[int, ...], tuple]:
        """Projected Free Hit gain in g, decided before `decided` (squad and data as of then)."""
        key = (decided, g)
        if key not in fh_cache:
            # Give the solver a Free Hit window covering g, whatever the manager really had left.
            st_ = replace(state(decided), chips=(ChipWindow(FREE_HIT, g, g),))
            pool = build_pool(_W["data"].bootstrap, _W["projections"][decided], st_, (g,), available=_W["exists"][g])
            fh_cache[key] = free_hit_week(pool, st_, g, discount=0.0)
        return fh_cache[key]

    def projected(chip: str, decided: int, g: int) -> float:
        if chip == FREE_HIT:
            return free_hit(decided, g)[0]
        x = _xpts(decided, g)
        squad = state(decided).element_ids
        fn = bench_boost_week if chip == BENCH_BOOST else triple_captain_week
        return fn(squad, _W["position"], x)[0]

    def actual(chip: str, g: int, real: bool = False) -> float | None:
        pk = picks.get(g)
        if pk is None:
            return None
        if chip == FREE_HIT:
            x = _xpts(g, g)
            before = _model_score(state(g).element_ids, g, x)
            if real:  # the manager's own Free Hit squad, with the model's lineup
                return _model_score([p.element for p in pk.picks], g, x) - before
            _, _, squad = free_hit(g, g)
            return _model_score(squad, g, x) - before
        starting, bench, captain, vice = _real_lineup(pk)
        return _score(starting, bench, captain, vice, g, chip) - _score(starting, bench, captain, vice, g)

    out: dict[str, Any] = {"entry": manager["entry"], "band": manager["band"], "chips": {}}
    for chip in CHIPS:
        weeks = [g for g in range(start, end + 1) if g in picks and g - 1 in picks and real_chips.get(g) in (None, chip)]
        if not weeks:
            continue
        gains = {g: actual(chip, g) for g in weeks}
        gains = {g: v for g, v in gains.items() if v is not None}
        if not gains:
            continue
        chosen = {}
        for rule in ("best", "early"):
            for g in weeks:
                if g not in gains:
                    continue
                remaining = [h for h in weeks if h >= g and h in gains]
                values = {h: projected(chip, g, h) for h in remaining}
                top = max(values.values())
                now = values[g] >= top - 1e-9 if rule == "best" else values[g] >= top - CLOSE
                if now or g == remaining[-1]:
                    chosen[rule] = g
                    break
        row = {
            "gains": gains,
            "best": chosen.get("best"), "early": chosen.get("early"),
            "real": next((g for g, c in real_chips.items() if c == chip and start <= g <= end), None),
        }
        if row["real"] is not None and row["real"] in picks and row["real"] - 1 in picks:
            row["real_gain"] = actual(chip, row["real"], real=True)
        if chip == FREE_HIT:
            row["fh_projected"] = {g: free_hit(g, g)[0] for g in gains}
        out["chips"][chip] = row
    return out


def _task(manager: dict):
    try:
        return simulate(manager), None
    except Exception as e:
        return None, f"{manager['entry']}: {type(e).__name__}: {e}"


def run(start: int, end: int, workers: int) -> None:
    sample = [json.loads(f.read_text(encoding="utf-8")) for f in sorted(SAMPLE.glob("*.json")) if not f.name.startswith("_")]
    sample = [m for m in sample if str(end) in m["picks"]]
    data = load_live()
    projections = {
        g: project(data, train_through=g - 1, target_gws=list(range(g, end + 1)), use_availability=False)
        for g in range(start, end + 1)
    }
    exists = {g: frozenset(el.id for el in data.live[g].elements) for g in range(start, end + 1)}
    done = set()
    if OUT.exists():
        done = {json.loads(line)["entry"] for line in OUT.read_text(encoding="utf-8").splitlines() if line.strip()}
    todo = [m for m in sample if m["entry"] not in done]
    print(f"{len(sample)} managers with GW{end} picks; {len(todo)} to run; GW{start}-GW{end}", flush=True)
    started = time.perf_counter()
    with ProcessPoolExecutor(max_workers=workers, initializer=_init, initargs=(data, projections, exists, start, end)) as pool:
        futures = [pool.submit(_task, m) for m in todo]
        for i, fut in enumerate(as_completed(futures), 1):
            result, error = fut.result()
            if error:
                print(f"  failed {error}", flush=True)
            else:
                with open(OUT, "a", encoding="utf-8") as f:
                    f.write(json.dumps(result) + "\n")
            if i % 50 == 0 or i == len(futures):
                print(f"  {i}/{len(futures)} ({(time.perf_counter() - started) / 60:.0f} min)", flush=True)


def _ci(xs: list[float]) -> str:
    if len(xs) < 2:
        return "n/a"
    return f"±{2 * st.stdev(xs) / math.sqrt(len(xs)):.1f}"


def report() -> str:
    rows = [json.loads(line) for line in OUT.read_text(encoding="utf-8").splitlines() if line.strip()]
    lines = [
        f"{len(rows)} managers. Real points the chip added, averaged per manager.",
        "",
        "| Chip | Managers | Planner (best week) | Planner (earliest close week) | Average week | Best week in hindsight | Planner − average |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    matched_lines = [
        "",
        "Chip-matched: managers who really played the chip in the window, scored the same way.",
        "",
        "| Chip | Managers | Their week | Planner (best week) | Planner − them |",
        "| --- | --- | --- | --- | --- |",
    ]
    fh_proj, fh_real = [], []
    for chip in CHIPS:
        rs = [r["chips"][chip] for r in rows if chip in r["chips"] and r["chips"][chip]["best"] is not None]
        if not rs:
            continue
        g = lambda r, k: r["gains"][str(r[k])] if str(r[k]) in r["gains"] else r["gains"].get(r[k])
        best = [g(r, "best") for r in rs]
        early = [g(r, "early") for r in rs]
        avg = [st.mean(r["gains"].values()) for r in rs]
        top = [max(r["gains"].values()) for r in rs]
        diff = [b - a for b, a in zip(best, avg)]
        lines.append(
            f"| {CHIP_LABELS[chip]} | {len(rs)} | {st.mean(best):.2f} | {st.mean(early):.2f} | {st.mean(avg):.2f} | "
            f"{st.mean(top):.2f} | {st.mean(diff):+.2f} ({_ci(diff)}) |"
        )
        m = [r for r in rs if r.get("real_gain") is not None]
        if m:
            d = [g(r, "best") - r["real_gain"] for r in m]
            matched_lines.append(
                f"| {CHIP_LABELS[chip]} | {len(m)} | {st.mean(r['real_gain'] for r in m):.2f} | "
                f"{st.mean(g(r, 'best') for r in m):.2f} | {st.mean(d):+.2f} ({_ci(d)}) |"
            )
        if chip == FREE_HIT:
            for r in rs:
                for wk, proj in r["fh_projected"].items():
                    fh_proj.append(proj)
                    fh_real.append(r["gains"][wk])
    lines += matched_lines
    if fh_proj:
        lines += [
            "",
            f"Free Hit, every manager-week ({len(fh_proj)}): projected gain {st.mean(fh_proj):.2f}, real gain "
            f"{st.mean(fh_real):.2f} (real ÷ projected = {st.mean(fh_real) / st.mean(fh_proj):.2f}).",
        ]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from", dest="start", type=int, default=5)
    ap.add_argument("--to", dest="end", type=int, default=10)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if not args.report:
        run(args.start, args.end, args.workers)
    print(report())


if __name__ == "__main__":
    main()
