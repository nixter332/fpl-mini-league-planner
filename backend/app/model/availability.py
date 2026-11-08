"""Whether a player can play a given fixture, from FPL's status, chance of playing and news.

Rules (agreed with Nikhil):
- Status "u" (left the club, loaned out) → 0 for every fixture.
- A return date in the news ("Expected back 22 Nov", "Suspended until 29 Nov") → 0 for
  fixtures that kick off before that date, then fully available.
- Otherwise `chance_of_playing_next_round` applies to the next actionable GW only.
"""

import re
from datetime import date, datetime, timedelta

from app.fpl.models import Element

_RETURN_DATE = re.compile(r"(?:expected back|until)\s+(\d{1,2})\s+([A-Za-z]{3})", re.IGNORECASE)
_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}


def return_date(element: Element) -> date | None:
    """The date in the news text, with the year inferred from when the news was posted."""
    match = _RETURN_DATE.search(element.news or "")
    if not match:
        return None
    day, month = int(match.group(1)), _MONTHS.get(match.group(2).lower())
    if month is None:
        return None
    posted = (element.news_added or datetime.now()).date()
    try:
        candidate = date(posted.year, month, day)
        if candidate < posted - timedelta(days=7):  # e.g. posted in Oct, "back 2 Jan"
            candidate = date(posted.year + 1, month, day)
    except ValueError:
        return None
    return candidate


def availability(element: Element, kickoff: datetime | None, gw: int, next_gw: int) -> float:
    """Probability (0-1) the player is available for one fixture."""
    if element.status == "u":
        return 0.0
    back = return_date(element)
    if back is not None and kickoff is not None:
        return 0.0 if kickoff.date() < back else 1.0
    if gw == next_gw and element.chance_of_playing_next_round is not None:
        return element.chance_of_playing_next_round / 100
    return 1.0
