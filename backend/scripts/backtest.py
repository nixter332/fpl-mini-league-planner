"""Backtest the expected-points model against FPL's ep_next and a points-per-game baseline.

Usage (from backend/):
    python -m scripts.backtest                 # offline, from tests/fixtures
    python -m scripts.backtest --live          # through the cached FPL client (finished GWs)
    python -m scripts.backtest --from 4 --to 9

Each GW k is predicted using only live data from GWs < k. See app/model/backtest.py.
"""

import argparse
import json
from pathlib import Path

import pandas as pd

from app.fpl.models import Bootstrap, EventLive, Fixture
from app.model.backtest import backtest, summarise
from app.model.history import SeasonData

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"


def load_from_fixtures(folder: Path = FIXTURES, finished_only: bool = True) -> SeasonData:
    def load(name: str):
        return json.loads((folder / name).read_text(encoding="utf-8"))

    manifest = load("manifest.json")
    last = manifest["latest_finished_gw"] if finished_only else manifest["latest_started_gw"]
    live = {int(gw): EventLive.model_validate(load(name)) for gw, name in manifest["files"]["event_live"].items() if int(gw) <= last}
    return SeasonData(
        Bootstrap.model_validate(load(manifest["files"]["bootstrap"])),
        [Fixture.model_validate(f) for f in load(manifest["files"]["fixtures"])],
        live,
    )


def load_live() -> SeasonData:
    from app.fpl.client import FPLClient
    from app.fpl.gameweeks import latest_finished_gameweek

    with FPLClient() as client:
        bootstrap = Bootstrap.model_validate(client.bootstrap())
        last = latest_finished_gameweek(bootstrap.events)
        live = {gw: EventLive.model_validate(client.event_live(gw)) for gw in range(1, (last.id if last else 0) + 1)}
        fixtures = [Fixture.model_validate(f) for f in client.fixtures()]
    return SeasonData(bootstrap, fixtures, live)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--live", action="store_true", help="Use the FPL API (cached) instead of saved fixtures")
    parser.add_argument("--from", dest="start", type=int, default=4, help="First GW to predict (default 4)")
    parser.add_argument("--to", dest="end", type=int, help="Last GW to predict (default: latest finished)")
    args = parser.parse_args()

    data = load_live() if args.live else load_from_fixtures()
    end = args.end or max(data.live)
    results = backtest(data, range(args.start, end + 1))

    pd.set_option("display.width", 200)
    print(f"Mean absolute error per player-GW, GW{args.start}-{end} (lower is better)\n")
    for population, label in (("played", "Players who played"), ("had_fixture", "Every player with a fixture")):
        table = results[results["population"] == population].drop(columns="population")
        print(label)
        print(table.round(2).to_string(index=False))
        print()
    print("Overall (weighted by players)")
    print(summarise(results).round(3).to_string())


if __name__ == "__main__":
    main()
