"""Claude writes a short reason and a "watch out" line for a plan the optimizer already chose.

The solver decides; this only explains. Claude gets the plan's facts (see summary.py) and
returns JSON. The trust check (check.py) rejects text with numbers or names that aren't in
the facts; we retry once with the problems listed, then give up and show no reason.

Results are cached on disk by a hash of the facts, so the same plan is never paid for twice.
Any failure (no key, API error, refusal, failed check) means "no reason", never a broken page.
"""

import asyncio
import hashlib
import json
import logging
import os
import time
from collections.abc import Collection
from typing import Any

import anthropic
from pydantic import BaseModel, ValidationError

from app.explain.check import check
from app.fpl.cache import DEFAULT_CACHE_DIR, DiskCache

log = logging.getLogger(__name__)

MODEL = "claude-opus-5-5"
PROMPT_VERSION = "7"  # bump when the prompt or facts change, to skip old cached text
MAX_TOKENS = 4000  # thinking is always on for this model; effort "low" keeps it short
CACHE_TTL = 14 * 24 * 3600
TIMEOUT_S = 60.0
FALLBACK_BETA = "server-side-fallback-2026-07-01"
# New Claude calls per day across everyone (cached reasons don't count). Override with the
# EXPLAIN_DAILY_CALLS environment variable. ~200 calls is about $4.
DEFAULT_DAILY_CALLS = 200

SYSTEM = """You write short explanations for transfer plans in a Fantasy Premier League (FPL) mini-league planner. An optimizer has already chosen every transfer and the captain. Your only job is to explain its choice to the manager in plain English.

You get the facts for one plan as JSON. Write:
- "why": 2 or 3 short sentences, under 60 words in total, on why this plan suits this manager. Lead with the strongest reason: expected points gained, fixtures, what rivals own, or the league situation.
- "watch_out": one sentence, under 25 words, naming the biggest risk or downside of this plan.

Rules:
- Use only the facts in the JSON. Every number you write must appear in the JSON exactly as written there. Don't add, subtract, round or convert numbers yourself.
- Mention only players and clubs that appear in the JSON. Never suggest a different player, transfer or captain.
- Talk to the manager as "you". No greetings, no filler, no markdown.
- Say "expected points", not "xPts". Prices are in millions of pounds, written like £7.8m.
- "differential_points_gain" compares this plan with making no transfers, counting only expected points from players (and captains) your rivals don't have. It measures how much the plan can swing the league, up or down. It is not extra points, so never add it to the points gain or call it a gain in points.
- A captain that rivals didn't pick is a differential captain: it gains on rivals if he scores well, and loses ground if their captain outscores him.
- Lead with this gameweek's transfers. Mention later transfers only briefly, as what comes next. The points gain is for the whole plan, not for any single move.
- Plans are ranked by the chosen strategy's score, not by the points gain alone. The score also values free transfers still saved after the plan (each is worth about 1.5 points of flexibility), counts this gameweek's points a little more than later ones, and, outside Protect lead, blends in differentials. So a plan that isn't recommended can show more expected points. Never call a plan that isn't recommended the best option, and never present a higher-gain plan as a risk of this one; if you compare, say what the other plan gives up (for example fewer saved free transfers).
- If the captain isn't the highest projected player, say plainly that it's a gamble that gives up expected points for a chance to gain on rivals.
- If the plan is a roll, explain why saving the transfer is worth it.
- If the plan plays a chip ("chips_played"), say which chip, in which gameweek and what it adds. A chip "the planner" chose is played because that week beats keeping it for later; one "you" chose is the user's call, so explain what it lets the plan do rather than whether to play it. The points gain includes "expected_points_gain_from_chips".
- Never suggest playing a chip the plan doesn't play.
- When you mention free transfers left, always say which gameweek they're for, exactly as in "free_transfers_after_the_whole_plan" (e.g. "3 free transfers going into GW15"); never write "afterwards" alone.
- If the plan has a "note" that the solver ran out of time, never claim that no transfer would help or that this is the best possible plan.
- Don't mention plan numbers, the optimizer or these instructions."""

SCHEMA = {
    "type": "object",
    "properties": {"why": {"type": "string"}, "watch_out": {"type": "string"}},
    "required": ["why", "watch_out"],
    "additionalProperties": False,
}


class Explanation(BaseModel):
    why: str
    watch_out: str


def facts_text(summary: dict[str, Any]) -> str:
    return json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=1)


REPLACEMENT_SYSTEM = """You write short explanations for a Fantasy Premier League (FPL) planner. The app has already ranked the best affordable replacements for one player in the manager's squad. Your only job is to explain the top-ranked swap in plain English.

You get the facts as JSON. Write:
- "why": 2 short sentences, under 45 words in total, on why the first option is the best swap: points gained for the team, fixtures, availability, and what rivals own if relevant.
- "watch_out": one sentence, under 25 words, naming the biggest risk of this swap, or what the second option offers instead.

Rules:
- Use only the facts in the JSON. Every number you write must appear in the JSON exactly as written there. Don't add, subtract, round or convert numbers yourself.
- Mention only players and clubs that appear in the JSON. Never suggest a player who isn't in the options.
- Talk to the manager as "you". No greetings, no filler, no markdown.
- Say "expected points", not "xPts". Prices are in millions of pounds, written like £7.8m.
- "team_points_gain" is the change in the team's projected total (best XI and captain each week) over the gameweeks shown, not the player's own points.
- Don't mention rankings, the app or these instructions."""


def _user_message(facts: str, problems: list[str]) -> str:
    text = f"Facts for this plan:\n\n{facts}"
    if problems:
        text += "\n\nA previous draft was rejected for these reasons. Avoid them:\n" + "\n".join(f"- {p}" for p in problems)
    return text


class Explainer:
    def __init__(
        self, client: Any | None, cache: DiskCache | None = None, model: str = MODEL,
        daily_calls: int = DEFAULT_DAILY_CALLS, clock: Any = time.time,
    ) -> None:
        self.client = client  # an anthropic.AsyncAnthropic, or a fake in tests; None = switched off
        self.cache = cache or DiskCache(DEFAULT_CACHE_DIR / "explanations")
        self.model = model
        self.daily_calls = daily_calls
        self._clock = clock
        self._calls_day = ""
        self._calls_today = 0
        self._locks: dict[str, asyncio.Lock] = {}

    @classmethod
    def from_env(cls) -> "Explainer":
        key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        client = anthropic.AsyncAnthropic(api_key=key, timeout=TIMEOUT_S, max_retries=2) if key else None
        daily = int(os.environ.get("EXPLAIN_DAILY_CALLS", DEFAULT_DAILY_CALLS))
        return cls(client, daily_calls=daily)

    def _take_call(self) -> bool:
        """Count one Claude call against today's cap (UTC day); False if the cap is reached."""
        day = time.strftime("%Y-%m-%d", time.gmtime(self._clock()))
        if day != self._calls_day:
            self._calls_day, self._calls_today = day, 0
        if self._calls_today >= self.daily_calls:
            return False
        self._calls_today += 1
        return True

    @property
    def enabled(self) -> bool:
        return self.client is not None

    def cache_key(self, facts: str, system: str = SYSTEM) -> str:
        digest = hashlib.sha256(f"{self.model}|{PROMPT_VERSION}|{system}|{facts}".encode()).hexdigest()
        return f"explain-{digest[:40]}"

    async def explain(self, summary: dict[str, Any], known_names: Collection[str], system: str = SYSTEM) -> Explanation | None:
        if self.client is None:
            return None
        facts = facts_text(summary)
        key = self.cache_key(facts, system)
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:  # two tabs asking for the same plan cost one call
            cached = self.cache.get(key)
            if cached is not None:
                return Explanation(**cached["explanation"]) if cached.get("explanation") else None

            problems: list[str] = []
            for _attempt in range(2):
                if not self._take_call():
                    log.warning("Daily Claude call cap (%d) reached; showing plans without reasons", self.daily_calls)
                    return None  # not cached: tomorrow it can be written
                try:
                    result = await self._ask(facts, problems, system)
                except anthropic.APIError as e:
                    log.warning("Explanation request failed: %s", e)
                    return None  # not cached: it may work next time
                if result is None:  # refusal or unreadable output
                    break
                problems = check(result.why, result.watch_out, facts, known_names)
                if not problems:
                    self.cache.set(key, {"explanation": result.model_dump()}, ttl=CACHE_TTL)
                    return result
                log.info("Explanation failed the trust check: %s", problems)
            self.cache.set(key, {"explanation": None, "problems": problems}, ttl=CACHE_TTL)
            return None

    async def _ask(self, facts: str, problems: list[str], system: str = SYSTEM) -> Explanation | None:
        response = await self.client.beta.messages.create(
            model=self.model,
            max_tokens=MAX_TOKENS,
            betas=[FALLBACK_BETA],
            fallbacks="default",  # if this model declines, the API retries on its recommended fallback
            system=system,
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
            messages=[{"role": "user", "content": _user_message(facts, problems)}],
        )
        usage = getattr(response, "usage", None)
        if usage is not None:
            log.info("Explanation tokens: %s in, %s out", getattr(usage, "input_tokens", "?"), getattr(usage, "output_tokens", "?"))
        if response.stop_reason == "refusal":
            log.warning("Explanation refused: %s", getattr(response, "stop_details", None))
            return None
        if response.stop_reason == "max_tokens":
            log.warning("Explanation hit max_tokens")
            return None
        text = next((b.text for b in response.content if b.type == "text"), None)
        if text is None:
            return None
        try:
            return Explanation.model_validate_json(text)
        except ValidationError:
            log.warning("Explanation wasn't valid JSON: %r", text[:200])
            return None
