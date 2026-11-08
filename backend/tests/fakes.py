"""Fakes for tests: an FPL API serving the saved fixtures, and a Claude client (no live calls)."""

import json
from types import SimpleNamespace
from typing import Any

import httpx

from tests.conftest import load_fixture


def fixture_routes(manifest: dict[str, Any]) -> dict[str, Any]:
    """URL path (and query) -> saved JSON, mirroring the real API layout."""
    files = manifest["files"]
    team, league, gw = manifest["team_id"], manifest["league_id"], manifest["latest_started_gw"]
    captain = int(files["element_summary"].removeprefix("element-summary-").removesuffix(".json"))
    table: dict[str, Any] = {
        "/api/bootstrap-static/": load_fixture(files["bootstrap"]),
        "/api/fixtures/": load_fixture(files["fixtures"]),
        f"/api/element-summary/{captain}/": load_fixture(files["element_summary"]),
        f"/api/entry/{team}/": load_fixture(files["entry"]),
        f"/api/entry/{team}/history/": load_fixture(files["history"]),
        f"/api/entry/{team}/transfers/": load_fixture(files["transfers"]),
        f"/api/entry/{team}/event/{gw}/picks/": load_fixture(files["picks"]),
    }
    for live_gw, name in files["event_live"].items():
        table[f"/api/event/{live_gw}/live/"] = load_fixture(name)
    for page, name in enumerate(files["standings_pages"], start=1):
        table[f"/api/leagues-classic/{league}/standings/?page_standings={page}"] = load_fixture(name)
    for rival, name in files["rival_picks"].items():
        table[f"/api/entry/{rival}/event/{gw}/picks/"] = load_fixture(name)
    return table


class FakeFPL:
    """An httpx transport that serves `routes`, records requests and can inject failures."""

    def __init__(self, routes: dict[str, Any]) -> None:
        self.routes = routes
        self.requests: list[httpx.Request] = []
        self.failures: list[httpx.Response | Exception] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.failures:
            failure = self.failures.pop(0)
            if isinstance(failure, Exception):
                raise failure
            return failure
        key = request.url.path + (f"?{request.url.query.decode()}" if request.url.query else "")
        if key not in self.routes:
            return httpx.Response(404, json={"detail": "Not found."})
        return httpx.Response(200, json=self.routes[key])


class FakeClaude:
    """Stands in for anthropic.AsyncAnthropic: returns canned replies and records each request.

    A reply is a dict ({"why", "watch_out"}), an Exception to raise, or a full response object.
    """

    def __init__(self, *replies: Any) -> None:
        self.replies = list(replies)
        self.calls: list[dict[str, Any]] = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(reply, Exception):
            raise reply
        if isinstance(reply, dict):
            return claude_reply(json.dumps(reply))
        return reply


def claude_reply(text: str | None, stop_reason: str = "end_turn") -> SimpleNamespace:
    content = [SimpleNamespace(type="thinking", thinking="")]
    if text is not None:
        content.append(SimpleNamespace(type="text", text=text))
    return SimpleNamespace(
        stop_reason=stop_reason, stop_details=None, content=content,
        usage=SimpleNamespace(input_tokens=900, output_tokens=120),
    )
