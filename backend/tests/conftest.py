"""Shared test setup. Tests read saved fixtures only; any real network call fails."""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

FIXTURES = Path(__file__).parent / "fixtures"

# Never use a real Claude key in tests, even if backend/.env has one: an empty value here
# stops load_dotenv from filling it in, so the app's explainer stays switched off.
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["WARM_UP"] = "0"  # tests build their own services; no background start-up work


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
        chip_defs=bootstrap.chips,
    )


@pytest.fixture(scope="session")
def rival_picks(manifest):
    from app.fpl.models import EntryPicks

    return [EntryPicks.model_validate(load_fixture(n)) for n in manifest["files"]["rival_picks"].values()]


@pytest.fixture(scope="session")
def api(manifest: dict[str, Any], snapshot_time: datetime, tmp_path_factory: pytest.TempPathFactory):
    """The FastAPI app on a fake FPL server built from the saved fixtures (shared: plans are slow)."""
    from fastapi.testclient import TestClient

    from app.api.main import app, set_service
    from app.api.service import PlannerService
    from app.fpl.cache import DiskCache
    from app.fpl.client import FPLClient
    from tests.fakes import FakeFPL, fixture_routes

    fake = FakeFPL(fixture_routes(manifest))
    client = FPLClient(
        DiskCache(tmp_path_factory.mktemp("cache"), clock=lambda: snapshot_time.timestamp()),
        transport=httpx.MockTransport(fake), sleep=lambda _: None, now=lambda: snapshot_time,
    )
    set_service(PlannerService(client, now=lambda: snapshot_time))
    yield TestClient(app)
    set_service(None)
