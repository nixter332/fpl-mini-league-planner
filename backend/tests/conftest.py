"""Shared test setup. Tests read saved fixtures only; any real network call fails."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def manifest() -> dict[str, Any]:
    return load_fixture("manifest.json")


@pytest.fixture(scope="session")
def snapshot_time(manifest: dict[str, Any]) -> datetime:
    return datetime.fromisoformat(manifest["fetched_at"])


@pytest.fixture(autouse=True)
def _block_real_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: object, **kwargs: object) -> None:
        raise RuntimeError("Tests must not call the live FPL API; use tests/fixtures.")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", refuse)


@pytest.fixture(scope="session")
def season():
    """Bootstrap, fixtures and live data for every finished GW in the snapshot."""
    from scripts.backtest import load_from_fixtures

    return load_from_fixtures(FIXTURES, finished_only=True)


@pytest.fixture(scope="session")
def season_with_current():
    """As `season`, plus the in-progress GW (matches the bootstrap snapshot moment)."""
    from scripts.backtest import load_from_fixtures

    return load_from_fixtures(FIXTURES, finished_only=False)


@pytest.fixture(scope="session")
def manager_state(manifest):
    """Nikhil's squad state from the snapshot (GW10 picks, for GW11)."""
    from app.fpl.models import Bootstrap, EntryHistory, EntryPicks, Transfer
    from app.optimizer.state import build_state

    files = manifest["files"]
    bootstrap = Bootstrap.model_validate(load_fixture(files["bootstrap"]))
    return build_state(
        manifest["team_id"],
        EntryPicks.model_validate(load_fixture(files["picks"])),
        manifest["latest_started_gw"],
        EntryHistory.model_validate(load_fixture(files["history"])),
        [Transfer.model_validate(t) for t in load_fixture(files["transfers"])],
        {e.id: e for e in bootstrap.elements},
    )


@pytest.fixture(scope="session")
def rival_picks(manifest):
    from app.fpl.models import EntryPicks

    return [EntryPicks.model_validate(load_fixture(n)) for n in manifest["files"]["rival_picks"].values()]
