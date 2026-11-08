"""Every saved fixture parses into our models, and the fields we rely on hold real values."""

from typing import Any

from app.fpl.models import (
    Bootstrap,
    ElementSummary,
    Entry,
    EntryHistory,
    EntryPicks,
    EventLive,
    Fixture,
    LeagueStandings,
    Transfer,
)
from tests.conftest import load_fixture


def test_bootstrap(manifest: dict[str, Any]) -> None:
    b = Bootstrap.model_validate(load_fixture(manifest["files"]["bootstrap"]))
    assert len(b.events) == 38
    assert len(b.teams) == 20
    assert [t.singular_name_short for t in b.element_types] == ["GKP", "DEF", "MID", "FWD"]
    assert [t.squad_select for t in b.element_types] == [2, 5, 5, 3]
    assert len(b.elements) > 500

    rules = b.game_config.rules
    assert (rules.squad_squadsize, rules.squad_team_limit, rules.squad_total_spend) == (15, 3, 1000)
    assert rules.max_extra_free_transfers == 4  # so free transfers cap at 5
    assert rules.transfers_sell_on_fee == 0.5

    # String decimals became floats; prices stay ints.
    assert all(isinstance(e.expected_goals, float) for e in b.elements)
    assert all(isinstance(e.now_cost, int) and 35 <= e.now_cost <= 160 for e in b.elements)
    # The defensive contribution signal is real (v0 read a non-existent field and got 0).
    assert max(e.defensive_contribution for e in b.elements if e.element_type == 2) > 0
    # Start price is recoverable for players held since GW1.
    assert all(e.start_cost == e.now_cost - e.cost_change_start for e in b.elements)


def test_fixtures(manifest: dict[str, Any]) -> None:
    fixtures = [Fixture.model_validate(f) for f in load_fixture(manifest["files"]["fixtures"])]
    assert len(fixtures) == 380
    assert all(1 <= f.team_h_difficulty <= 5 for f in fixtures)
    assert all(f.team_h != f.team_a for f in fixtures)


def test_event_live(manifest: dict[str, Any]) -> None:
    for name in manifest["files"]["event_live"].values():
        live = EventLive.model_validate(load_fixture(name))
        assert len(live.elements) > 500
        played = [e for e in live.elements if e.stats.minutes > 0]
        assert played, name
        assert all(e.explain for e in played)


def test_element_summary(manifest: dict[str, Any]) -> None:
    summary = ElementSummary.model_validate(load_fixture(manifest["files"]["element_summary"]))
    assert summary.history and summary.fixtures
    assert all(h.value > 0 for h in summary.history)


def test_entry(manifest: dict[str, Any]) -> None:
    entry = Entry.model_validate(load_fixture(manifest["files"]["entry"]))
    assert entry.id == manifest["team_id"]
    assert manifest["league_id"] in {lg.id for lg in entry.leagues.classic}


def test_entry_history(manifest: dict[str, Any]) -> None:
    history = EntryHistory.model_validate(load_fixture(manifest["files"]["history"]))
    assert [h.event for h in history.current] == sorted(h.event for h in history.current)
    assert all(h.event_transfers_cost % 4 == 0 for h in history.current)


def test_transfers(manifest: dict[str, Any]) -> None:
    transfers = [Transfer.model_validate(t) for t in load_fixture(manifest["files"]["transfers"])]
    assert transfers
    assert all(t.element_in_cost > 0 and t.element_out_cost > 0 for t in transfers)


def test_picks(manifest: dict[str, Any]) -> None:
    names = [manifest["files"]["picks"], *manifest["files"]["rival_picks"].values()]
    for name in names:
        picks = EntryPicks.model_validate(load_fixture(name))
        assert len(picks.picks) == 15
        assert sum(p.is_captain for p in picks.picks) == 1
        assert sum(p.is_vice_captain for p in picks.picks) == 1
        assert [p.position for p in picks.picks] == list(range(1, 16))
        assert all(p.multiplier == 0 for p in picks.picks if p.position > 11) or picks.active_chip == "bboost"


def test_league_standings(manifest: dict[str, Any]) -> None:
    pages = [LeagueStandings.model_validate(load_fixture(n)) for n in manifest["files"]["standings_pages"]]
    assert pages[0].league.id == manifest["league_id"]
    assert pages[-1].standings.has_next is False
    rows = [r for p in pages for r in p.standings.results]
    assert manifest["team_id"] in {r.entry for r in rows}
