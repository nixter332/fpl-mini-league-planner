"""Team attack and defence ratings from past matches (FPL's own strength fields are empty).

Model: expected goals for team T against O = base[venue] * attack[T] * defence[O], where
ratings average 1.0. Each match's "observed" goals blend xG and real goals; recent matches
weigh more, and every team is pulled toward average by a few pseudo-matches so early-season
ratings don't swing on one result. Ratings are fitted by a few rounds of opponent adjustment.
"""

from collections.abc import Iterable
from dataclasses import dataclass

import pandas as pd

LEAGUE_HOME_GOALS = 1.5  # priors when there's little or no data
LEAGUE_AWAY_GOALS = 1.2


@dataclass(frozen=True)
class TeamRatings:
    attack: dict[int, float]
    defence: dict[int, float]  # >1 means concedes more than average
    home_goals: float
    away_goals: float

    def expected_goals(self, team: int, opponent: int, home: bool) -> float:
        base = self.home_goals if home else self.away_goals
        return base * self.attack.get(team, 1.0) * self.defence.get(opponent, 1.0)

    def average_goals_for(self, team: int) -> float:
        """Team's expected goals against an average opponent, averaged over venues."""
        return (self.home_goals + self.away_goals) / 2 * self.attack.get(team, 1.0)

    def average_goals_against(self, team: int) -> float:
        return (self.home_goals + self.away_goals) / 2 * self.defence.get(team, 1.0)


def fit_team_ratings(
    matches: pd.DataFrame,
    teams: Iterable[int],
    *,
    decay: float = 0.92,
    xg_weight: float = 0.7,
    prior_matches: float = 4.0,
    iterations: int = 10,
) -> TeamRatings:
    teams = list(teams)
    if matches.empty:
        return TeamRatings({t: 1.0 for t in teams}, {t: 1.0 for t in teams}, LEAGUE_HOME_GOALS, LEAGUE_AWAY_GOALS)

    latest = matches["gw"].max()
    w = decay ** (latest - matches["gw"])
    obs_home = xg_weight * matches["xg_home"] + (1 - xg_weight) * matches["goals_home"]
    obs_away = xg_weight * matches["xg_away"] + (1 - xg_weight) * matches["goals_away"]

    prior_w = prior_matches
    home_goals = float((w * obs_home).sum() + prior_w * LEAGUE_HOME_GOALS) / float(w.sum() + prior_w)
    away_goals = float((w * obs_away).sum() + prior_w * LEAGUE_AWAY_GOALS) / float(w.sum() + prior_w)
    avg = (home_goals + away_goals) / 2

    attack = {t: 1.0 for t in teams}
    defence = {t: 1.0 for t in teams}
    home, away = matches["home"].to_numpy(), matches["away"].to_numpy()
    wv, oh, oa = w.to_numpy(), obs_home.to_numpy(), obs_away.to_numpy()

    for _ in range(iterations):
        att_num = {t: prior_w * avg for t in teams}
        att_den = {t: prior_w * avg for t in teams}
        def_num = {t: prior_w * avg for t in teams}
        def_den = {t: prior_w * avg for t in teams}
        for h, a, wi, gh, ga in zip(home, away, wv, oh, oa):
            # Home side attacking, away side defending, and vice versa.
            att_num[h] += wi * gh
            att_den[h] += wi * home_goals * defence[a]
            att_num[a] += wi * ga
            att_den[a] += wi * away_goals * defence[h]
            def_num[a] += wi * gh
            def_den[a] += wi * home_goals * attack[h]
            def_num[h] += wi * ga
            def_den[h] += wi * away_goals * attack[a]
        attack = _normalise({t: att_num[t] / att_den[t] for t in teams})
        defence = _normalise({t: def_num[t] / def_den[t] for t in teams})

    return TeamRatings(attack, defence, home_goals, away_goals)


def _normalise(ratings: dict[int, float]) -> dict[int, float]:
    mean = sum(ratings.values()) / len(ratings)
    return {t: r / mean for t, r in ratings.items()}
