"""Expected points for one player in one fixture, split into parts.

The parts are kept separate so later phases can explain a projection with real numbers.
"""

import math
from dataclasses import asdict, dataclass

from app.model.minutes import MinutesProfile
from app.model.rates import PlayerRates
from app.model.scoring import GKP, GOALS_CONCEDED_PER_POINT, SAVES_PER_POINT, ScoringRules

# In a double gameweek each match carries some rotation risk, so a DGW lands around 1.8x.
DGW_ROTATION = 0.9


@dataclass(frozen=True)
class FixtureContext:
    team_goals: float  # this team's expected goals in this fixture
    opponent_goals: float  # expected goals conceded in this fixture
    team_avg_goals: float  # this team's expected goals vs an average opponent
    team_avg_conceded: float
    n_team_fixtures: int  # fixtures this team has in this GW (2 = double)


@dataclass(frozen=True)
class PointsBreakdown:
    appearance: float
    goals: float
    assists: float
    clean_sheet: float
    goals_conceded: float
    saves: float
    defensive_contribution: float
    bonus: float
    cards: float

    @property
    def total(self) -> float:
        return sum(asdict(self).values())


ZERO = PointsBreakdown(0, 0, 0, 0, 0, 0, 0, 0, 0)


def fixture_points(
    position: int,
    minutes: MinutesProfile,
    rates: PlayerRates,
    ctx: FixtureContext,
    rules: ScoringRules,
    available: float = 1.0,
) -> PointsBreakdown:
    a = available * (DGW_ROTATION if ctx.n_team_fixtures > 1 else 1.0)
    if a <= 0:
        return ZERO

    p_appear = a * minutes.p_appear
    p_60 = a * min(minutes.p_60, minutes.p_appear)
    share = a * minutes.minutes / 90  # expected fraction of the match on the pitch
    attack_scale = ctx.team_goals / ctx.team_avg_goals if ctx.team_avg_goals > 0 else 1.0
    pressure_scale = ctx.opponent_goals / ctx.team_avg_conceded if ctx.team_avg_conceded > 0 else 1.0

    goals_conceded = 0.0
    if rules.goals_conceded[position]:
        goals_conceded = p_60 * expected_floor_div(ctx.opponent_goals, GOALS_CONCEDED_PER_POINT) * rules.goals_conceded[position]

    saves = 0.0
    if position == GKP:
        expected_saves = rates.saves90 * pressure_scale
        saves = p_60 * expected_floor_div(expected_saves, SAVES_PER_POINT) * rules.saves

    return PointsBreakdown(
        appearance=p_60 * rules.long_play + (p_appear - p_60) * rules.short_play,
        goals=rates.xg90 * share * attack_scale * rules.goals_scored[position],
        assists=rates.xa90 * share * attack_scale * rules.assists,
        clean_sheet=p_60 * math.exp(-ctx.opponent_goals) * rules.clean_sheets[position],
        goals_conceded=goals_conceded,
        saves=saves,
        defensive_contribution=p_60 * rates.dc_rate * rules.defensive_contribution[position],
        bonus=rates.bonus90 * share,
        cards=rates.yellow90 * share * rules.yellow_cards,
    )


def expected_floor_div(mean: float, k: int) -> float:
    """E[floor(X / k)] for X ~ Poisson(mean): e.g. points for every 3 saves or 2 goals conceded."""
    if mean <= 0:
        return 0.0
    total, p = 0.0, math.exp(-mean)
    for n in range(1, int(mean * 4 + 20)):
        p *= mean / n
        total += (n // k) * p
    return total
