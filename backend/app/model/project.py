"""Expected points per player per gameweek: the model's public entry point.

    data = SeasonData(bootstrap, fixtures, live)
    xpts = project(data, train_through=9, target_gws=[11, 12, 13, 14, 15])

Training uses only `event/{gw}/live/` for GWs <= `train_through`, so a backtest that sets
train_through = k - 1 can't see GW k.
"""

from collections.abc import Sequence
from dataclasses import asdict

import pandas as pd

from app.model.availability import availability
from app.model.history import SeasonData, player_gameweeks, team_matches
from app.model.minutes import DEFAULT_PROFILE, minutes_profiles
from app.model.points import FixtureContext, fixture_points
from app.model.rates import player_rates
from app.model.scoring import ScoringRules
from app.model.team_strength import fit_team_ratings

COMPONENTS = [
    "appearance", "goals", "assists", "clean_sheet", "goals_conceded",
    "saves", "defensive_contribution", "bonus", "cards",
]


def project_fixtures(
    data: SeasonData,
    *,
    train_through: int,
    target_gws: Sequence[int],
    use_availability: bool = True,
) -> pd.DataFrame:
    """One row per player per fixture in the target GWs, with each points component."""
    train = SeasonData(data.bootstrap, data.fixtures, {gw: lv for gw, lv in data.live.items() if gw <= train_through})
    history = player_gameweeks(train)
    ratings = fit_team_ratings(team_matches(train, history), [t.id for t in data.bootstrap.teams])
    minutes = minutes_profiles(history)
    rates = player_rates(history, data.bootstrap.elements)
    rules = ScoringRules.from_game_config(data.bootstrap.game_config.scoring)

    targets = set(target_gws)
    next_gw = min(targets)
    by_team: dict[int, list] = {}
    for f in data.fixtures:
        if f.event in targets:
            by_team.setdefault(f.team_h, []).append((f, f.team_a, True))
            by_team.setdefault(f.team_a, []).append((f, f.team_h, False))

    rows = []
    for e in data.bootstrap.elements:
        for f, opponent, home in by_team.get(e.team, []):
            n_in_gw = sum(1 for g, _, _ in by_team[e.team] if g.event == f.event)
            ctx = FixtureContext(
                team_goals=ratings.expected_goals(e.team, opponent, home),
                opponent_goals=ratings.expected_goals(opponent, e.team, not home),
                team_avg_goals=ratings.average_goals_for(e.team),
                team_avg_conceded=ratings.average_goals_against(e.team),
                n_team_fixtures=n_in_gw,
            )
            avail = availability(e, f.kickoff_time, f.event, next_gw) if use_availability else 1.0
            breakdown = fixture_points(
                e.element_type, minutes.get(e.id, DEFAULT_PROFILE), rates[e.id], ctx, rules, avail
            )
            rows.append(
                {
                    "element": e.id,
                    "gw": f.event,
                    "fixture": f.id,
                    "opponent": opponent,
                    "home": home,
                    "available": avail,
                    "team_goals": ctx.team_goals,
                    "opponent_goals": ctx.opponent_goals,
                    **asdict(breakdown),
                    "xpts": breakdown.total,
                }
            )
    columns = ["element", "gw", "fixture", "opponent", "home", "available", "team_goals", "opponent_goals", *COMPONENTS, "xpts"]
    return pd.DataFrame(rows, columns=columns)


def project(
    data: SeasonData,
    *,
    train_through: int,
    target_gws: Sequence[int],
    use_availability: bool = True,
) -> pd.DataFrame:
    """One row per player per target GW (fixtures summed; 0 in a blank), indexed by (element, gw)."""
    per_fixture = project_fixtures(
        data, train_through=train_through, target_gws=target_gws, use_availability=use_availability
    )
    summed = per_fixture.groupby(["element", "gw"])[[*COMPONENTS, "xpts"]].sum()
    summed["n_fixtures"] = per_fixture.groupby(["element", "gw"]).size()

    grid = pd.MultiIndex.from_product(
        [[e.id for e in data.bootstrap.elements], sorted(set(target_gws))], names=["element", "gw"]
    )
    return summed.reindex(grid, fill_value=0)
