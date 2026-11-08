"""The client against a fake FPL server that serves the saved fixtures (no network)."""

import copy
import tempfile
import time
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.fpl.cache import DiskCache
from app.fpl.client import LIVE_IN_PROGRESS_TTL, SHORT_TTL, USER_AGENT, FPLClient, FPLError, FPLNotFound
from tests.conftest import load_fixture
from tests.fakes import FakeFPL, fixture_routes


@pytest.fixture(scope="module")
def routes(manifest: dict[str, Any]) -> dict[str, Any]:
    return fixture_routes(manifest)


class Clock:
    def __init__(self, start: datetime) -> None:
        self.now = start

    def wall(self) -> float:
        return self.now.timestamp()

    def utc(self) -> datetime:
        return self.now


@pytest.fixture
def clock(snapshot_time: datetime) -> Clock:
    return Clock(snapshot_time)


@pytest.fixture
def fake(routes: dict[str, Any]) -> FakeFPL:
    return FakeFPL(routes)


@pytest.fixture
def sleeps() -> list[float]:
    return []


@pytest.fixture
def make_client(tmp_path: Path, fake: FakeFPL, clock: Clock, sleeps: list[float]) -> Callable[..., FPLClient]:
    def make(**kwargs: Any) -> FPLClient:
        return FPLClient(
            DiskCache(tmp_path, clock=clock.wall),
            transport=httpx.MockTransport(fake),
            sleep=sleeps.append,
            monotonic=lambda: 0.0,  # every request looks back-to-back, so throttling always sleeps
            now=clock.utc,
            **kwargs,
        )

    return make


def test_every_endpoint_loads_from_fixtures_and_is_cached(
    make_client: Callable[..., FPLClient], fake: FakeFPL, manifest: dict[str, Any], routes: dict[str, Any]
) -> None:
    team, league, gw = manifest["team_id"], manifest["league_id"], manifest["latest_started_gw"]
    captain = int(manifest["files"]["element_summary"].removeprefix("element-summary-").removesuffix(".json"))
    live_gw = manifest["latest_finished_gw"]
    calls: list[tuple[Callable[[FPLClient], Any], str]] = [
        (lambda c: c.bootstrap(), "/api/bootstrap-static/"),
        (lambda c: c.fixtures(), "/api/fixtures/"),
        (lambda c: c.event_live(live_gw), f"/api/event/{live_gw}/live/"),
        (lambda c: c.element_summary(captain), f"/api/element-summary/{captain}/"),
        (lambda c: c.entry(team), f"/api/entry/{team}/"),
        (lambda c: c.entry_history(team), f"/api/entry/{team}/history/"),
        (lambda c: c.entry_transfers(team), f"/api/entry/{team}/transfers/"),
        (lambda c: c.entry_picks(team, gw), f"/api/entry/{team}/event/{gw}/picks/"),
        (lambda c: c.league_standings(league), f"/api/leagues-classic/{league}/standings/?page_standings=1"),
    ]
    client = make_client()
    for call, route in calls:
        assert call(client) == routes[route], route
    first_pass = client.network_calls

    # A fresh client on the same cache folder: everything is a cache hit.
    again = make_client()
    for call, route in calls:
        assert call(again) == routes[route], route
    assert again.network_calls == 0
    assert len(fake.requests) == first_pass


def test_user_agent_and_json_accept(make_client: Callable[..., FPLClient], fake: FakeFPL) -> None:
    make_client().bootstrap()
    assert fake.requests[0].headers["User-Agent"] == USER_AGENT
    assert fake.requests[0].headers["Accept"] == "application/json"


def test_bootstrap_expires_at_next_deadline(
    make_client: Callable[..., FPLClient], clock: Clock, routes: dict[str, Any], manifest: dict[str, Any]
) -> None:
    client = make_client()
    client.bootstrap()
    next_gw = next(e for e in routes["/api/bootstrap-static/"]["events"] if e["id"] == manifest["next_actionable_gw"])
    deadline = datetime.fromisoformat(next_gw["deadline_time"].replace("Z", "+00:00"))

    # The 6h refresh is sooner than the deadline here, so it expires after 6h.
    clock.now += timedelta(hours=6)
    client.bootstrap()
    assert client.network_calls == 2

    # Just before the deadline it's still cached (6h after the last fetch hasn't passed)...
    clock.now = deadline - timedelta(minutes=1)
    client.bootstrap()
    calls = client.network_calls
    clock.now = deadline - timedelta(seconds=30)
    client.bootstrap()
    assert client.network_calls == calls
    # ...and the deadline itself forces a refetch even though 6h haven't passed.
    clock.now = deadline
    client.bootstrap()
    assert client.network_calls == calls + 1


def test_finished_gw_live_never_expires_in_progress_does(
    make_client: Callable[..., FPLClient], clock: Clock, manifest: dict[str, Any]
) -> None:
    client = make_client()
    client.event_live(manifest["latest_finished_gw"])
    client.event_live(manifest["latest_started_gw"])  # in progress at snapshot time
    base = client.network_calls

    clock.now += timedelta(seconds=LIVE_IN_PROGRESS_TTL)
    client.event_live(manifest["latest_finished_gw"])
    assert client.network_calls == base  # finished GW: still cached
    client.event_live(manifest["latest_started_gw"])
    assert client.network_calls == base + 1


def test_manager_data_expires_after_short_ttl(
    make_client: Callable[..., FPLClient], clock: Clock, manifest: dict[str, Any]
) -> None:
    client = make_client()
    client.entry(manifest["team_id"])
    clock.now += timedelta(seconds=SHORT_TTL - 1)
    client.entry(manifest["team_id"])
    assert client.network_calls == 1
    clock.now += timedelta(seconds=1)
    client.entry(manifest["team_id"])
    assert client.network_calls == 2


def test_retries_with_backoff_then_succeeds(
    make_client: Callable[..., FPLClient], fake: FakeFPL, sleeps: list[float], routes: dict[str, Any]
) -> None:
    fake.failures = [httpx.Response(503), httpx.ConnectError("boom"), httpx.Response(429, headers={"Retry-After": "7"})]
    client = make_client(backoff=1.0, min_interval=0)
    assert client.bootstrap() == routes["/api/bootstrap-static/"]
    assert len(fake.requests) == 4
    assert sleeps == [1.0, 2.0, 7.0]  # exponential backoff, then honours Retry-After


def test_gives_up_after_max_retries(make_client: Callable[..., FPLClient], fake: FakeFPL) -> None:
    fake.failures = [httpx.Response(502)] * 10
    with pytest.raises(FPLError, match="after 3 attempts"):
        make_client(max_retries=2).bootstrap()
    assert len(fake.requests) == 3


def test_not_found_is_not_retried(make_client: Callable[..., FPLClient], fake: FakeFPL) -> None:
    with pytest.raises(FPLNotFound):
        make_client().entry(999_999_999)
    assert len(fake.requests) == 1


def test_non_json_response_is_a_clear_error(make_client: Callable[..., FPLClient], fake: FakeFPL) -> None:
    fake.failures = [httpx.Response(200, text="The game is being updated.")]
    with pytest.raises(FPLError, match="did not return JSON"):
        make_client().bootstrap()


def test_bulk_picks_are_throttled_and_tolerate_missing(
    make_client: Callable[..., FPLClient], sleeps: list[float], manifest: dict[str, Any]
) -> None:
    client = make_client(bulk_interval=1.0, min_interval=0)
    client.bootstrap()
    rivals = [int(r) for r in manifest["files"]["rival_picks"]]
    sleeps.clear()
    result = client.many_entry_picks([*rivals, 999_999_999], manifest["latest_started_gw"])
    assert set(result) == {*rivals, 999_999_999}
    assert result[999_999_999] is None
    assert all(result[r]["picks"] for r in rivals)
    assert sleeps and all(s == pytest.approx(1.0) for s in sleeps)


def test_standings_pagination_follows_has_next(
    make_client: Callable[..., FPLClient], fake: FakeFPL, manifest: dict[str, Any]
) -> None:
    league = manifest["league_id"]
    page1 = load_fixture(manifest["files"]["standings_pages"][0])
    first, second = copy.deepcopy(page1), copy.deepcopy(page1)
    first["standings"]["has_next"] = True
    second["standings"].update(page=2, has_next=False)
    fake.routes = {
        **fake.routes,
        f"/api/leagues-classic/{league}/standings/?page_standings=1": first,
        f"/api/leagues-classic/{league}/standings/?page_standings=2": second,
    }
    pages = make_client().league_standings_all(league)
    assert [p["standings"]["page"] for p in pages] == [1, 2]


def test_throttle_is_shared_across_threads() -> None:
    """The rival prefetch runs in a background thread; FPL must still see one request at a time."""
    import threading

    stamps: list[float] = []
    lock = threading.Lock()

    def handler(request: httpx.Request) -> httpx.Response:
        with lock:
            stamps.append(time.monotonic())
        return httpx.Response(200, json={"ok": True})

    client = FPLClient(DiskCache(Path(tempfile.mkdtemp())), transport=httpx.MockTransport(handler), min_interval=0.05)
    threads = [threading.Thread(target=client._get_json, args=(f"x/{i}/",)) for i in range(6)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    gaps = [b - a for a, b in zip(sorted(stamps), sorted(stamps)[1:])]
    assert len(stamps) == 6 and min(gaps) >= 0.045
