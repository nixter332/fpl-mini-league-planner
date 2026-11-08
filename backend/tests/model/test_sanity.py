"""The sanity checks from docs/SPEC.md, run on the real GW10 snapshot."""

import pandas as pd
import pytest

from app.fpl.models import Fixture
from app.model.history import SeasonData
from app.model.project import project

TRAIN_THROUGH = 9
TARGETS = [11, 12, 13, 14]


def _project(data: SeasonData, **kwargs) -> pd.DataFrame:
    return project(data, train_through=TRAIN_THROUGH, target_gws=TARGETS, **kwargs)


def _with_element(data: SeasonData, element_id: int, **changes) -> SeasonData:
    bootstrap = data.bootstrap.model_copy(deep=True)
    bootstrap.elements = [e.model_copy(update=changes) if e.id == element_id else e for e in bootstrap.elements]
    return SeasonData(bootstrap, data.fixtures, data.live)


def _with_fixtures(data: SeasonData, fixtures: list[Fixture]) -> SeasonData:
    return SeasonData(data.bootstrap, fixtures, data.live)


@pytest.fixture(scope="module")
def baseline(season: SeasonData) -> pd.DataFrame:
    return _project(season)


@pytest.fixture(scope="module")
def premium(season: SeasonData):
    """The most expensive fit player (Haaland in the snapshot)."""
    fit = [e for e in season.bootstrap.elements if e.status == "a" and e.chance_of_playing_next_round in (None, 100)]
    return max(fit, key=lambda e: e.now_cost)


def test_projections_are_in_a_plausible_range(baseline: pd.DataFrame) -> None:
    assert baseline["xpts"].min() >= -1.0
    assert baseline["xpts"].max() <= 15.0
    regulars = baseline[baseline["appearance"] > 1.8]  # very likely to play 60+
    assert 2.0 < regulars["xpts"].mean() < 6.0


def test_top_premium_is_a_top_five_projection(baseline: pd.DataFrame, premium) -> None:
    """Model-level guard against the v0 Haaland bug (the solver-level check comes in phase 3)."""
    totals = baseline.groupby("element")["xpts"].sum().sort_values(ascending=False)
    assert premium.id in totals.head(5).index


def test_one_quiet_week_does_not_sink_a_premium(season: SeasonData, baseline: pd.DataFrame, premium) -> None:
    live = {gw: lv.model_copy(deep=True) for gw, lv in season.live.items()}
    for el in live[TRAIN_THROUGH].elements:
        if el.id == premium.id:
            el.stats.total_points, el.stats.goals_scored, el.stats.assists, el.stats.bonus = 2, 0, 0, 0
            el.stats.expected_goals, el.stats.expected_assists = 0.0, 0.0
    quiet = _project(SeasonData(season.bootstrap, season.fixtures, live))
    before = baseline.loc[premium.id, "xpts"].sum()
    after = quiet.loc[premium.id, "xpts"].sum()
    assert after < before  # it does register
    assert after > 0.85 * before  # but doesn't sink him


def test_injured_player_projects_zero(season: SeasonData, baseline: pd.DataFrame, premium) -> None:
    hurt = _project(_with_element(season, premium.id, status="i", chance_of_playing_next_round=0, news="Knock - 0% chance of playing"))
    assert hurt.loc[(premium.id, TARGETS[0]), "xpts"] == 0
    # With no return date, the chance covers the next GW only (agreed rule).
    assert hurt.loc[(premium.id, TARGETS[1]), "xpts"] == pytest.approx(baseline.loc[(premium.id, TARGETS[1]), "xpts"])


def test_injured_with_return_date_projects_zero_until_back(season: SeasonData, premium) -> None:
    gw13_kickoffs = [f.kickoff_time for f in season.fixtures if f.event == 13 and premium.team in (f.team_h, f.team_a)]
    back = gw13_kickoffs[0].date()
    news = f"Hamstring injury - Expected back {back.day} {back.strftime('%b')}"
    hurt = _project(_with_element(season, premium.id, status="i", chance_of_playing_next_round=0, news=news))
    assert hurt.loc[(premium.id, 11), "xpts"] == 0
    assert hurt.loc[(premium.id, 12), "xpts"] == 0
    assert hurt.loc[(premium.id, 13), "xpts"] > 0


def test_departed_player_projects_zero_everywhere(season: SeasonData, premium) -> None:
    gone = _project(_with_element(season, premium.id, status="u", chance_of_playing_next_round=0, news="Has joined Al Hilal permanently"))
    assert (gone.loc[premium.id, "xpts"] == 0).all()


def test_blank_gameweek_projects_zero(season: SeasonData, baseline: pd.DataFrame, premium) -> None:
    fixtures = [f for f in season.fixtures if not (f.event == 12 and premium.team in (f.team_h, f.team_a))]
    blank = _project(_with_fixtures(season, fixtures))
    assert blank.loc[(premium.id, 12), "xpts"] == 0
    assert blank.loc[(premium.id, 12), "n_fixtures"] == 0
    assert blank.loc[(premium.id, 11), "xpts"] == pytest.approx(baseline.loc[(premium.id, 11), "xpts"])


def test_double_gameweek_projects_1_6_to_2x(season: SeasonData, baseline: pd.DataFrame, premium) -> None:
    original = next(f for f in season.fixtures if f.event == 12 and premium.team in (f.team_h, f.team_a))
    extra = original.model_copy(update={"id": 99_999, "team_h": original.team_a, "team_a": original.team_h})
    double = _project(_with_fixtures(season, [*season.fixtures, extra]))

    team = {e.id: e.team for e in season.bootstrap.elements}
    regulars = [
        el for el in baseline.index.get_level_values("element").unique()
        if team[el] == premium.team and baseline.loc[(el, 12), "appearance"] > 1.5
    ]
    assert regulars
    for el in regulars:
        assert double.loc[(el, 12), "n_fixtures"] == 2
        ratio = double.loc[(el, 12), "xpts"] / baseline.loc[(el, 12), "xpts"]
        assert 1.6 <= ratio <= 2.0, (el, ratio)
