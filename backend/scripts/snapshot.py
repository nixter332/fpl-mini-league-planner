"""Save raw FPL responses for one manager and league as test fixtures.

Usage (from backend/):
    python -m scripts.snapshot --team 5179483 --league 1883627 [--rivals 20] [--out tests/fixtures]

Fetches every endpoint the app uses for the latest started gameweek (plus live data for
every gameweek so far, used by the model backtest) and writes the raw JSON,
plus a manifest.json describing what was saved. Requests go through the normal client, so
they're cached, throttled and retried.
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.fpl.client import FPLClient
from app.fpl.gameweeks import latest_finished_gameweek, latest_started_gameweek, next_actionable_gameweek
from app.fpl.models import Event

DEFAULT_OUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures"


def save(out: Path, name: str, data: Any) -> str:
    path = out / f"{name}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"  saved {path.name} ({path.stat().st_size // 1024} KB)")
    return path.name


def snapshot(team_id: int, league_id: int, rivals: int, out: Path) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    files: dict[str, Any] = {}

    with FPLClient() as client:
        print("Shared data")
        bootstrap = client.bootstrap()
        files["bootstrap"] = save(out, "bootstrap-static", bootstrap)
        files["fixtures"] = save(out, "fixtures", client.fixtures())

        events = [Event.model_validate(e) for e in bootstrap["events"]]
        started = latest_started_gameweek(events, now)
        finished = latest_finished_gameweek(events)
        actionable = next_actionable_gameweek(events, now)
        if started is None:
            sys.exit("No gameweek has started yet this season; nothing to snapshot.")

        live_gws = list(range(1, started.id + 1))  # every GW so far, for the model backtest
        files["event_live"] = {
            str(gw): save(out, f"event-{gw}-live", client.event_live(gw)) for gw in live_gws
        }

        print(f"Manager {team_id}")
        files["entry"] = save(out, f"entry-{team_id}", client.entry(team_id))
        files["history"] = save(out, f"entry-{team_id}-history", client.entry_history(team_id))
        files["transfers"] = save(out, f"entry-{team_id}-transfers", client.entry_transfers(team_id))
        picks = client.entry_picks(team_id, started.id)
        files["picks"] = save(out, f"entry-{team_id}-event-{started.id}-picks", picks)

        captain = next(p["element"] for p in picks["picks"] if p.get("is_captain"))
        files["element_summary"] = save(out, f"element-summary-{captain}", client.element_summary(captain))

        print(f"League {league_id}")
        pages = client.league_standings_all(league_id)
        files["standings_pages"] = [
            save(out, f"league-{league_id}-standings-p{i}", page) for i, page in enumerate(pages, start=1)
        ]

        members = [r for page in pages for r in page["standings"]["results"]]
        rival_ids = [r["entry"] for r in sorted(members, key=lambda r: r["rank"]) if r["entry"] != team_id]
        rival_ids = rival_ids[:rivals]
        print(f"Rivals' picks for GW{started.id} ({len(rival_ids)} managers, throttled)")
        rival_picks = client.many_entry_picks(rival_ids, started.id)
        files["rival_picks"] = {
            str(rid): save(out, f"entry-{rid}-event-{started.id}-picks", data)
            for rid, data in rival_picks.items()
            if data is not None
        }
        network_calls = client.network_calls

    manifest = {
        "fetched_at": now.isoformat(),
        "team_id": team_id,
        "league_id": league_id,
        "latest_started_gw": started.id,
        "latest_finished_gw": finished.id if finished else None,
        "next_actionable_gw": actionable.id if actionable else None,
        "files": files,
    }
    save(out, "manifest", manifest)
    print(f"Done: {network_calls} live requests (the rest came from the cache).")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--team", type=int, required=True, help="FPL team (entry) ID")
    parser.add_argument("--league", type=int, required=True, help="Classic league ID")
    parser.add_argument("--rivals", type=int, default=20, help="How many top rivals' picks to save")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Output folder")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)
    snapshot(args.team, args.league, args.rivals, args.out)


if __name__ == "__main__":
    main()
