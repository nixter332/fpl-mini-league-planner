"""Collect a sample of managers' histories, transfers and weekly picks for tuning.

Groups (each manager is saved once, in the first group that has them):
- leagues:   every member of Nikhil's leagues (rivals = the other members)
- overall:   50 managers at each of ranks ~1k, ~10k, ~100k and ~1M in the overall league
- india_top: the top 200 of the India league

One request per second (polite bulk rate), resumable: each manager is written to
data/cache/manager-sample/{entry}.json as soon as it's complete, and skipped next time.
Finished gameweeks' picks also land in the normal disk cache for good.

Usage (from backend/):  python -m scripts.collect_managers --to 9
"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from app.fpl.client import FPLClient, FPLNotFound
from app.fpl.models import Bootstrap, LeagueStandings
from app.fpl.gameweeks import latest_finished_gameweek

OUT = Path("data/cache/manager-sample")
LEAGUES = [1883627, 1863820, 1145494]
OVERALL, INDIA = 314, 120
OVERALL_PAGES = {"rank ~1k": 20, "rank ~10k": 200, "rank ~100k": 2000, "rank ~1M": 20000}
INDIA_PAGES = [1, 2, 3, 4]


def sample(client: FPLClient) -> list[dict[str, Any]]:
    """[{entry, name, group, band, league}] in group order."""
    rows: list[dict[str, Any]] = []
    for league in LEAGUES:
        for r in LeagueStandings.model_validate(client.league_standings(league)).standings.results:
            rows.append({"entry": r.entry, "name": r.player_name, "group": "leagues", "band": "Nikhil's leagues", "league": league})
    for band, page in OVERALL_PAGES.items():
        for r in LeagueStandings.model_validate(client.league_standings(OVERALL, page)).standings.results:
            rows.append({"entry": r.entry, "name": r.player_name, "group": "overall", "band": band, "league": None})
    for page in INDIA_PAGES:
        for r in LeagueStandings.model_validate(client.league_standings(INDIA, page)).standings.results:
            rows.append({"entry": r.entry, "name": r.player_name, "group": "india_top", "band": "India top 200", "league": None})
    seen: set[int] = set()
    out = []
    for row in rows:
        if row["entry"] not in seen:
            seen.add(row["entry"])
            out.append(row)
    return out


def collect_one(client: FPLClient, row: dict[str, Any], last_gw: int) -> dict[str, Any]:
    picks: dict[str, Any] = {}
    for gw in range(1, last_gw + 1):
        try:
            picks[str(gw)] = client.entry_picks(row["entry"], gw)
        except FPLNotFound:  # joined after this GW
            continue
    return {
        **row,
        "history": client.entry_history(row["entry"]),
        "transfers": client.entry_transfers(row["entry"]),
        "picks": picks,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--to", type=int, default=None, help="last GW to collect picks for (default: latest finished)")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    OUT.mkdir(parents=True, exist_ok=True)

    with FPLClient(min_interval=1.0) as client:  # one request a second for the whole run
        last = args.to or latest_finished_gameweek(Bootstrap.model_validate(client.bootstrap()).events).id
        rows = sample(client)
        (OUT / "_sample.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
        todo = [r for r in rows if not (OUT / f"{r['entry']}.json").exists()]
        print(f"{len(rows)} managers in the sample, {len(todo)} to collect (picks GW1-{last})", flush=True)
        started = time.perf_counter()
        for i, row in enumerate(todo, 1):
            try:
                data = collect_one(client, row, last)
            except Exception as e:  # keep going; a rerun retries the ones that failed
                print(f"  {row['entry']} failed: {e}", flush=True)
                continue
            (OUT / f"{row['entry']}.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            if i % 25 == 0 or i == len(todo):
                mins = (time.perf_counter() - started) / 60
                print(f"  {i}/{len(todo)} done ({mins:.0f} min, {client.network_calls} requests)", flush=True)


if __name__ == "__main__":
    main()
