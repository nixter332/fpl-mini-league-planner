"""Season data is refreshed in the background instead of making a request wait."""

import time
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any

import httpx

from app.api import service as service_mod
from app.api.service import PlannerService
from app.fpl.cache import DiskCache
from app.fpl.client import FPLClient
from tests.fakes import FakeFPL, fixture_routes


def make(manifest: dict[str, Any], now: datetime, tmp_path) -> PlannerService:
    client = FPLClient(
        DiskCache(tmp_path, clock=lambda: now.timestamp()),
        transport=httpx.MockTransport(FakeFPL(fixture_routes(manifest))), sleep=lambda _: None, now=lambda: now,
    )
    return PlannerService(client, now=lambda: now)


def test_stale_data_is_served_while_a_fresh_copy_builds(manifest, snapshot_time, tmp_path) -> None:
    svc = make(manifest, snapshot_time, tmp_path)
    first = svc.context()
    svc._context = replace(first, built_at=first.built_at - service_mod.CONTEXT_TTL - 1)  # a bit stale
    stale = svc._context
    assert svc.context() is stale  # answered at once from the old copy
    deadline = time.monotonic() + 30
    while svc._context is stale and time.monotonic() < deadline:
        time.sleep(0.05)
    assert svc._context is not stale and svc._context.built_at > stale.built_at


def test_very_old_data_is_rebuilt_before_answering(manifest, snapshot_time, tmp_path) -> None:
    svc = make(manifest, snapshot_time, tmp_path)
    first = svc.context()
    svc._context = replace(first, built_at=first.built_at - service_mod.CONTEXT_MAX_AGE - 1)
    assert svc.context().built_at > first.built_at - 1


def test_data_from_before_a_deadline_is_rebuilt(manifest, snapshot_time, tmp_path) -> None:
    svc = make(manifest, snapshot_time, tmp_path)
    ctx = svc.context()
    deadline = ctx.events[ctx.gws[0]].deadline_time
    svc._now = lambda: deadline + timedelta(minutes=1)  # the deadline has just passed
    assert svc._must_rebuild(ctx)
