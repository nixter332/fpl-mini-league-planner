"""The Claude explainer, with a fake client: request shape, caching, retries and failures."""

import asyncio
from pathlib import Path

import anthropic
import httpx2
import pytest

from app.explain.explainer import FALLBACK_BETA, MODEL, Explainer, Explanation
from app.fpl.cache import DiskCache
from tests.fakes import FakeClaude, claude_reply

SUMMARY = {"plan": {"transfers": [{"in": {"name": "Saka"}, "out": {"name": "Palmer"}}], "gain": 4.2}, "this_gameweek": "GW12"}
KNOWN = {"Saka", "Palmer", "Haaland"}
GOOD = {"why": "Saka gains you 4.2 expected points over Palmer from GW12.", "watch_out": "Palmer could haul without you."}
BAD = {"why": "Bring in Haaland for 9.9 points.", "watch_out": "None."}


def run(explainer: Explainer, summary: dict = SUMMARY) -> Explanation | None:
    return asyncio.run(explainer.explain(summary, KNOWN))


@pytest.fixture
def cache(tmp_path: Path) -> DiskCache:
    return DiskCache(tmp_path)


def test_good_reply_is_returned_and_cached(cache: DiskCache) -> None:
    fake = FakeClaude(GOOD)
    explainer = Explainer(fake, cache)
    assert run(explainer) == Explanation(**GOOD)
    assert run(Explainer(fake, cache)) == Explanation(**GOOD)  # a fresh explainer reads the disk cache
    assert len(fake.calls) == 1


def test_request_shape(cache: DiskCache) -> None:
    fake = FakeClaude(GOOD)
    run(Explainer(fake, cache))
    call = fake.calls[0]
    assert call["model"] == MODEL == "claude-opus-5-5"
    assert call["betas"] == [FALLBACK_BETA] and call["fallbacks"] == "default"
    assert call["output_config"]["effort"] == "low"
    assert call["output_config"]["format"]["schema"]["required"] == ["why", "watch_out"]
    assert "Saka" in call["messages"][0]["content"]
    assert "Never suggest a different player" in call["system"]


def test_failed_check_retries_once_with_the_problems(cache: DiskCache) -> None:
    fake = FakeClaude(BAD, GOOD)
    assert run(Explainer(fake, cache)) == Explanation(**GOOD)
    assert len(fake.calls) == 2
    retry = fake.calls[1]["messages"][0]["content"]
    assert "rejected" in retry and "Haaland" in retry and "9.9" in retry


def test_failing_twice_gives_no_reason_and_is_not_retried_later(cache: DiskCache) -> None:
    fake = FakeClaude(BAD)
    assert run(Explainer(fake, cache)) is None
    assert run(Explainer(fake, cache)) is None
    assert len(fake.calls) == 2  # both on the first request; the second hit the cache


def test_refusal_and_bad_output_give_no_reason(cache: DiskCache) -> None:
    assert run(Explainer(FakeClaude(claude_reply(None, stop_reason="refusal")), cache)) is None
    other = {"plan": "different facts"}
    assert run(Explainer(FakeClaude(claude_reply("not json")), cache), other) is None


def test_api_errors_give_no_reason_and_are_not_cached(cache: DiskCache) -> None:
    error = anthropic.APIConnectionError(request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages"))
    assert run(Explainer(FakeClaude(error), cache)) is None
    fake = FakeClaude(GOOD)
    assert run(Explainer(fake, cache)) == Explanation(**GOOD)  # next time it works
    assert len(fake.calls) == 1


def test_no_key_means_switched_off(cache: DiskCache, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    explainer = Explainer.from_env()
    assert not explainer.enabled
    assert run(explainer) is None


def test_cache_key_changes_with_the_facts(cache: DiskCache) -> None:
    e = Explainer(None, cache)
    assert e.cache_key("a") != e.cache_key("b")
    assert e.cache_key("a") == Explainer(None, cache).cache_key("a")
