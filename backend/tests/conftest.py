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
