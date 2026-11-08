import pytest

from app.fpl.links import LinkParseError, ParsedLink, parse_link


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("5179483", ParsedLink(type="team", id=5179483)),
        ("  5179483  ", ParsedLink(type="team", id=5179483)),
        ("https://fantasy.premierleague.com/entry/5179483/event/10", ParsedLink(type="team", id=5179483)),
        ("fantasy.premierleague.com/entry/5179483/event/10/", ParsedLink(type="team", id=5179483)),
        ("https://fantasy.premierleague.com/entry/5179483/history", ParsedLink(type="team", id=5179483)),
        ("http://www.fantasy.premierleague.com/entry/5179483/", ParsedLink(type="team", id=5179483)),
        ("https://FANTASY.premierleague.com/entry/5179483/event/3?foo=bar#x", ParsedLink(type="team", id=5179483)),
        ("https://fantasy.premierleague.com/leagues/1883627/standings/c", ParsedLink(type="league", id=1883627)),
        ("fantasy.premierleague.com/leagues/1883627/standings/c/", ParsedLink(type="league", id=1883627)),
        ("https://fantasy.premierleague.com/leagues/1883627/standings/c?phase=1", ParsedLink(type="league", id=1883627)),
    ],
)
def test_valid_inputs(raw: str, expected: ParsedLink) -> None:
    assert parse_link(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "0",
        "-5",
        "abc",
        "https://example.com/entry/5179483/event/10",
        "https://fantasy.premierleague.com/",
        "https://fantasy.premierleague.com/my-team",
        "https://fantasy.premierleague.com/entry/abc/history",
        "https://fantasy.premierleague.com/entry/5179483/transfers",
        "https://fantasy.premierleague.com.evil.com/entry/5179483/history",
    ],
)
def test_invalid_inputs_raise_friendly_error(raw: str) -> None:
    with pytest.raises(LinkParseError) as exc:
        parse_link(raw)
    assert "We accept" in str(exc.value)
