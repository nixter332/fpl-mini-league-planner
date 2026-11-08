from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from app.fpl.gameweeks import (
    latest_finished_gameweek,
    latest_started_gameweek,
    next_actionable_gameweek,
    next_deadline,
)
from app.fpl.models import Bootstrap, Event
from tests.conftest import load_fixture


@pytest.fixture(scope="module")
def events(manifest: dict[str, Any]) -> list[Event]:
    return Bootstrap.model_validate(load_fixture(manifest["files"]["bootstrap"])).events


def test_real_snapshot(events: list[Event], snapshot_time: datetime, manifest: dict[str, Any]) -> None:
    # Snapshot was taken mid-GW10 (deadline passed, not finished): plan for GW11.
    assert next_actionable_gameweek(events, snapshot_time).id == manifest["next_actionable_gw"]
    assert latest_started_gameweek(events, snapshot_time).id == manifest["latest_started_gw"]
    assert latest_finished_gameweek(events).id == manifest["latest_finished_gw"]
    # Agrees with FPL's own flags at that moment.
    assert next_actionable_gameweek(events, snapshot_time).is_next


def _gw(gw_id: int, deadline: datetime, finished: bool = False) -> Event:
    return Event(
        id=gw_id,
        name=f"Gameweek {gw_id}",
        deadline_time=deadline,
        finished=finished,
        data_checked=finished,
        is_current=False,
        is_next=False,
        is_previous=False,
    )


T0 = datetime(2026, 8, 21, 17, 30, tzinfo=timezone.utc)
SEASON = [_gw(i, T0 + timedelta(days=7 * (i - 1))) for i in range(1, 39)]


def test_before_season_plans_gw1() -> None:
    assert next_actionable_gameweek(SEASON, T0 - timedelta(days=1)).id == 1
    assert latest_started_gameweek(SEASON, T0 - timedelta(days=1)) is None


def test_deadline_moment_rolls_to_next_gw() -> None:
    gw5_deadline = SEASON[4].deadline_time
    assert next_actionable_gameweek(SEASON, gw5_deadline - timedelta(seconds=1)).id == 5
    assert next_actionable_gameweek(SEASON, gw5_deadline).id == 6


def test_finished_current_gw_plans_next() -> None:
    events = [_gw(1, T0, finished=True), _gw(2, T0 + timedelta(days=7))]
    assert next_actionable_gameweek(events, T0 + timedelta(days=3)).id == 2


def test_after_last_deadline_returns_none() -> None:
    after = SEASON[-1].deadline_time + timedelta(hours=1)
    assert next_actionable_gameweek(SEASON, after) is None
    assert next_deadline(SEASON, after) is None


def test_order_of_events_does_not_matter() -> None:
    now = SEASON[9].deadline_time + timedelta(hours=1)
    assert next_actionable_gameweek(list(reversed(SEASON)), now).id == 11
