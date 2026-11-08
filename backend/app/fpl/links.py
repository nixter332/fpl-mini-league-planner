"""Turn whatever the user pastes (team ID, team link, league link) into a typed ID."""

import re
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel

SUPPORTED_FORMATS = (
    "a team ID (e.g. 1234567), "
    "a team link (fantasy.premierleague.com/entry/1234567/event/10 or /entry/1234567/history), "
    "or a league link (fantasy.premierleague.com/leagues/123456/standings/c)"
)

FPL_HOSTS = {"fantasy.premierleague.com", "www.fantasy.premierleague.com"}

_TEAM_PATH = re.compile(r"^/entry/(\d+)(?:/(?:event/\d+|history))?/?$")
_LEAGUE_PATH = re.compile(r"^/leagues/(\d+)(?:/standings(?:/c)?)?/?$")


class ParsedLink(BaseModel):
    type: Literal["team", "league"]
    id: int


class LinkParseError(ValueError):
    """Raised when the input isn't a format we recognise. Message is safe to show users."""


def parse_link(raw: str) -> ParsedLink:
    text = raw.strip()
    if not text:
        raise LinkParseError(f"Please paste something. We accept {SUPPORTED_FORMATS}.")

    if text.isdigit():
        return ParsedLink(type="team", id=_positive(text))

    url = text if "://" in text else f"https://{text}"
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if host not in FPL_HOSTS:
        raise LinkParseError(
            f"That doesn't look like a Fantasy Premier League link. We accept {SUPPORTED_FORMATS}."
        )

    path = parts.path or "/"
    if match := _TEAM_PATH.match(path):
        return ParsedLink(type="team", id=_positive(match.group(1)))
    if match := _LEAGUE_PATH.match(path):
        return ParsedLink(type="league", id=_positive(match.group(1)))

    raise LinkParseError(
        f"We couldn't find a team or league in that link. We accept {SUPPORTED_FORMATS}."
    )


def _positive(digits: str) -> int:
    value = int(digits)
    if value <= 0:
        raise LinkParseError(f"IDs must be greater than zero. We accept {SUPPORTED_FORMATS}.")
    return value
