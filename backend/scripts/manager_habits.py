"""How the collected managers play, by group, and how the model's picks compare on their squads.

Reads data/cache/manager-sample/ (python -m scripts.collect_managers). For each group:
points, transfers, hits, rolls, chip timing, most-captained players, and, on each manager's own
squad every week (no Bench Boost / Triple Captain weeks): the model's XI and captain against
theirs, scored with real points and FPL auto-subs.

Usage (from backend/):  python -m scripts.manager_habits --from 2 --to 9
"""

import argparse
import json
import statistics as st
import sys
from collections import Counter, defaultdict
from pathlib import Path

from app.fpl.models import EntryHistory, EntryPicks
from app.model.habits import captain_of, habits
from app.model.project import project
from app.optimizer.lineup import best_lineup
from app.optimizer.simulate import score_week
from scripts.backtest import load_live

SAMPLE = Path("data/cache/manager-sample")
GROUP_ORDER = ["Nikhil's leagues", "rank ~1M", "rank ~100k", "rank ~10k", "rank ~1k", "India top 200"]


def load_sample() -> list[dict]:
    rows = []
    for f in sorted(SAMPLE.glob("*.json")):
        if not f.name.startswith("_"):
            rows.append(json.loads(f.read_text(encoding="utf-8")))
    return rows


def mean(xs) -> float:
    xs = list(xs)
    return st.mean(xs) if xs else float("nan")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from", dest="start", type=int, default=2)
    ap.add_argument("--to", dest="end", type=int, default=9)
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    data = load_live()
    pos = {e.id: e.element_type for e in data.bootstrap.elements}
    name = {e.id: e.web_name for e in data.bootstrap.elements}
    gws = range(args.start, args.end + 1)
    xpts = {}
    for gw in gws:
        df = project(data, train_through=gw - 1, target_gws=(gw,), use_availability=False)
        xpts[gw] = {int(e): float(v) for (e, _), v in df["xpts"].items()}
    live = {gw: {el.id: el.stats for el in data.live[gw].elements} for gw in gws}

    by_band: dict[str, list] = defaultdict(list)
    for m in load_sample():
        by_band[m["band"]].append(m)

    print(f"GW{args.start}-GW{args.end}. Transfers and hits leave out Wildcard and Free Hit weeks.\n")
    print("| Group | Managers | Points/GW | Transfers/GW | Hits/GW | Weeks rolled | Took any hit |")
    print("| --- | --- | --- | --- | --- | --- | --- |")
    stats = {}
    for band in [b for b in GROUP_ORDER if b in by_band]:
        hs = [habits(EntryHistory.model_validate(m["history"]), args.start, args.end) for m in by_band[band]]
        stats[band] = hs
        print(f"| {band} | {len(hs)} | {mean(h.points_per_gw for h in hs):.1f} | {mean(h.transfers_per_gw for h in hs):.2f} | "
              f"{mean(h.hits_per_gw for h in hs):.2f} | {mean(h.roll_share for h in hs):.0%} | {mean(1.0 if h.hits_per_gw > 0 else 0.0 for h in hs):.0%} |")

    print("\n| Group | Wildcard used by GW%d | Free Hit | Bench Boost | Triple Captain | Most common Wildcard GW |" % args.end)
    print("| --- | --- | --- | --- | --- | --- |")
    for band, hs in stats.items():
        used = lambda c: mean(1.0 if c in h.chips and h.chips[c] <= args.end else 0.0 for h in hs)
        wc = Counter(h.chips["wildcard"] for h in hs if "wildcard" in h.chips and h.chips["wildcard"] <= args.end)
        common = ", ".join(f"GW{g} ({n})" for g, n in wc.most_common(3)) or "—"
        print(f"| {band} | {used('wildcard'):.0%} | {used('freehit'):.0%} | {used('bboost'):.0%} | {used('3xc'):.0%} | {common} |")

    print("\nOn their own squads each week (no Bench Boost / Triple Captain weeks), real points:")
    print("| Group | Their XI + captain | Model's XI + captain | Same captain | Their captain pts | Model captain pts | Top captains |")
    print("| --- | --- | --- | --- | --- | --- | --- |")
    for band in stats:
        theirs, model, same, cap_t, cap_m = [], [], [], [], []
        caps: Counter = Counter()
        for m in by_band[band]:
            for gw in gws:
                raw = m["picks"].get(str(gw))
                if not raw:
                    continue
                pk = EntryPicks.model_validate(raw)
                if pk.active_chip in ("bboost", "3xc", "freehit"):
                    continue
                st_ = live[gw]
                mins = {e: s.minutes for e, s in st_.items()}
                pts = {e: s.total_points for e, s in st_.items()}
                ps = sorted(pk.picks, key=lambda p: p.position)
                cap = captain_of(pk)
                vice = next(p.element for p in ps if p.is_vice_captain)
                real = score_week([p.element for p in ps[:11]], [p.element for p in ps[11:]], cap, vice, pos, mins, pts)
                lu = best_lineup([p.element for p in ps], pos, xpts[gw])
                mod = score_week(lu.starting, lu.bench, lu.captain, lu.vice, pos, mins, pts)
                theirs.append(real.points)
                model.append(mod.points)
                same.append(1.0 if lu.captain == cap else 0.0)
                cap_t.append(pts.get(cap, 0))
                cap_m.append(pts.get(lu.captain, 0))
                caps[name[cap]] += 1
        total = sum(caps.values())
        top = ", ".join(f"{n} {c / total:.0%}" for n, c in caps.most_common(3))
        print(f"| {band} | {mean(theirs):.1f} | {mean(model):.1f} | {mean(same):.0%} | {mean(cap_t):.1f} | {mean(cap_m):.1f} | {top} |")


if __name__ == "__main__":
    main()
