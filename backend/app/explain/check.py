"""Trust check: Claude's text may only use numbers and names that are in the plan's facts.

Numbers: every number in the text must appear in the facts (compared after rounding to one
decimal, ignoring signs and thousands separators). Names: the text must not mention any player
or club we know of that isn't in the facts. Names we don't know (a nickname, a misspelling)
can't be checked; the prompt forbids them and this is the backstop for the common case.
"""

import re
from collections.abc import Collection
from functools import lru_cache

NUMBER = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?")
MAX_WHY_CHARS = 420
MAX_WATCH_CHARS = 200


def numbers_in(text: str) -> set[float]:
    return {round(float(m.replace(",", "")), 1) for m in NUMBER.findall(text)}


@lru_cache(maxsize=4096)
def _name_pattern(name: str) -> re.Pattern[str]:
    return re.compile(rf"(?<!\w){re.escape(name)}(?!\w)")


def names_in(text: str, names: Collection[str]) -> set[str]:
    return {n for n in names if n and _name_pattern(n).search(text)}


def _fmt(x: float) -> str:
    return f"{x:g}"


def check(why: str, watch_out: str, facts_text: str, known_names: Collection[str]) -> list[str]:
    """Problems with an explanation; empty means it passes."""
    problems = []
    if not why.strip() or not watch_out.strip():
        problems.append("Both 'why' and 'watch_out' must be filled in.")
    if len(why) > MAX_WHY_CHARS:
        problems.append(f"'why' is too long ({len(why)} characters; keep it under {MAX_WHY_CHARS}).")
    if len(watch_out) > MAX_WATCH_CHARS:
        problems.append(f"'watch_out' is too long ({len(watch_out)} characters; keep it under {MAX_WATCH_CHARS}).")

    allowed_numbers = numbers_in(facts_text)
    allowed_names = names_in(facts_text, known_names)
    others = set(known_names) - allowed_names
    for label, text in (("why", why), ("watch_out", watch_out)):
        for x in sorted(numbers_in(text) - allowed_numbers):
            problems.append(f"'{label}' uses the number {_fmt(x)}, which isn't in the facts.")
        # Blank out allowed names first, so "White" isn't found inside "Gibbs-White".
        scrubbed = text
        for name in sorted(allowed_names, key=len, reverse=True):
            scrubbed = _name_pattern(name).sub(" ", scrubbed)
        for name in sorted(names_in(scrubbed, others)):
            problems.append(f"'{label}' mentions {name}, who isn't in the facts.")
    return problems
