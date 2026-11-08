"""Per-player and per-match history rebuilt from `event/{gw}/live/` only.

This is the leakage-free source for the model: to predict GW k we filter these tables to
GWs < k. Nothing here reads bootstrap's season totals.
"""

from dataclasses import dataclass

import pandas as pd

from app.fpl.models import Bootstrap, EventLive, Fixture
from app.model.scoring import LONG_PLAY_MINUTES

PLAYER_COLUMNS = [
    "element", "gw", "team", "position", "n_fix", "minutes", "starts", "apps", "mins60",
    "points", "goals", "assists", "clean_sheets", "goals_conceded", "saves", "bonus",
    "yellow", "xg", "xa", "xgc", "dc", "dc_hits",
]
MATCH_COLUMNS = ["fixture", "gw", "home", "away", "xg_home", "xg_away", "goals_home", "goals_away"]


@dataclass(frozen=True)
class SeasonData:
    """Everything the model reads. Parsed once; cheap to filter."""

    bootstrap: Bootstrap
    fixtures: list[Fixture]
    live: dict[int, EventLive]


def player_gameweeks(data: SeasonData) -> pd.DataFrame:
    """One row per player per GW they were registered for.

    `n_fix` is how many fixtures the player's team had that GW (0 = blank), taken from the
    per-fixture `explain` entries, which FPL lists for every squad player, even on 0 minutes.
    `team` is the side the player was on, or -1 if it can't be told (moved between PL clubs).
    """
    positions = {e.id: e.element_type for e in data.bootstrap.elements}
    current_team = {e.id: e.team for e in data.bootstrap.elements}
    fixtures = {f.id: f for f in data.fixtures}
    dc_ids = {"defensive_contribution"}

    rows = []
    for gw, live in sorted(data.live.items()):
        for el in live.elements:
            if el.id not in positions:
                continue
            s = el.stats
            fixture_minutes = [_stat(fx.stats, "minutes") for fx in el.explain]
            dc_hits = sum(
                any(st.identifier in dc_ids and st.points > 0 for st in fx.stats) for fx in el.explain
            )
            rows.append(
                {
                    "element": el.id,
                    "gw": gw,
                    "team": _team_at(current_team[el.id], [fixtures.get(fx.fixture) for fx in el.explain]),
                    "position": positions[el.id],
                    "n_fix": len(el.explain),
                    "minutes": s.minutes,
                    "starts": s.starts,
                    "apps": sum(m > 0 for m in fixture_minutes),
                    "mins60": sum(m >= LONG_PLAY_MINUTES for m in fixture_minutes),
                    "points": s.total_points,
                    "goals": s.goals_scored,
                    "assists": s.assists,
                    "clean_sheets": s.clean_sheets,
                    "goals_conceded": s.goals_conceded,
                    "saves": s.saves,
                    "bonus": s.bonus,
                    "yellow": s.yellow_cards,
                    "xg": s.expected_goals,
                    "xa": s.expected_assists,
                    "xgc": s.expected_goals_conceded,
                    "dc": s.defensive_contribution,
                    "dc_hits": dc_hits,
                }
            )
    return pd.DataFrame(rows, columns=PLAYER_COLUMNS)


def team_matches(data: SeasonData, players: pd.DataFrame) -> pd.DataFrame:
    """One row per played fixture with each side's xG and goals.

    A team's xG against is the largest `expected_goals_conceded` among its players that GW
    (anyone who played the whole match carries the full team figure); its xG for is the
    opponent's xG against. In a double gameweek the GW figure is split evenly per fixture.
    """
    known = players[players["team"] >= 0]
    xg_against = known.groupby(["team", "gw"])["xgc"].max()
    n_fix = known.groupby(["team", "gw"])["n_fix"].max()

    rows = []
    for f in data.fixtures:
        if f.event is None or f.event not in data.live or f.team_h_score is None or f.team_a_score is None:
            continue
        h_key, a_key = (f.team_h, f.event), (f.team_a, f.event)
        if h_key not in xg_against.index or a_key not in xg_against.index:
            continue
        rows.append(
            {
                "fixture": f.id,
                "gw": f.event,
                "home": f.team_h,
                "away": f.team_a,
                "xg_home": xg_against[a_key] / max(n_fix[a_key], 1),
                "xg_away": xg_against[h_key] / max(n_fix[h_key], 1),
                "goals_home": f.team_h_score,
                "goals_away": f.team_a_score,
            }
        )
    return pd.DataFrame(rows, columns=MATCH_COLUMNS)


def _stat(stats: list, identifier: str) -> int:
    return next((s.value for s in stats if s.identifier == identifier), 0)


def _team_at(current: int, fixtures: list[Fixture | None]) -> int:
    for f in fixtures:
        if f is not None and current in (f.team_h, f.team_a):
            return current
    return current if not fixtures else -1
