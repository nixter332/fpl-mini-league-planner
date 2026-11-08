"""Unit tests for team strength, minutes, rates, availability and per-fixture points."""

import math
from datetime import datetime, timezone

import pandas as pd
import pytest

from app.model.availability import availability, return_date
from app.model.history import PLAYER_COLUMNS, SeasonData
from app.model.minutes import minutes_profiles
from app.model.points import DGW_ROTATION, FixtureContext, ZERO, expected_floor_div, fixture_points
from app.model.rates import player_rates
from app.model.minutes import MinutesProfile
from app.model.rates import PlayerRates
from app.model.scoring import DEF, FWD, GKP, MID, ScoringRules
from app.model.team_strength import fit_team_ratings


# ---- team strength ----------------------------------------------------------------------


def _match(gw: int, home: int, away: int, xh: float, xa: float, gh: int, ga: int) -> dict:
    return {"fixture": gw * 100 + home, "gw": gw, "home": home, "away": away,
            "xg_home": xh, "xg_away": xa, "goals_home": gh, "goals_away": ga}


def test_no_matches_gives_average_ratings() -> None:
    ratings = fit_team_ratings(pd.DataFrame(columns=list(_match(1, 1, 2, 0, 0, 0, 0))), [1, 2, 3])
    assert ratings.attack == {1: 1.0, 2: 1.0, 3: 1.0}
    assert ratings.expected_goals(1, 2, home=True) > ratings.expected_goals(1, 2, home=False)


def test_strong_attack_and_leaky_defence_are_detected() -> None:
    matches = pd.DataFrame(
        [_match(gw, h, a, 3.0 if h == 1 else 1.0, 3.0 if a == 1 else (2.5 if h == 2 else 1.0), 0, 0)
         for gw in range(1, 9) for h, a in ((1, 2), (3, 4), (2, 3), (4, 1))]
    )
    ratings = fit_team_ratings(matches, [1, 2, 3, 4])
    assert ratings.attack[1] == max(ratings.attack.values())
    assert ratings.defence[2] == max(ratings.defence.values())  # concedes 2.5-3 a game
    assert sum(ratings.attack.values()) / 4 == pytest.approx(1.0)
    assert sum(ratings.defence.values()) / 4 == pytest.approx(1.0)


def test_real_ratings_are_sensible(season: SeasonData) -> None:
    from app.model.history import player_gameweeks, team_matches

    history = player_gameweeks(season)
    ratings = fit_team_ratings(team_matches(season, history), [t.id for t in season.bootstrap.teams])
    assert 1.1 < ratings.home_goals < 2.0 and 0.8 < ratings.away_goals < 1.7
    assert all(0.4 < r < 2.0 for r in ratings.attack.values())
    assert all(0.4 < r < 2.0 for r in ratings.defence.values())


# ---- minutes ----------------------------------------------------------------------------


def _rows(element: int, minutes_by_gw: dict[int, int], n_fix: int = 1, position: int = MID) -> list[dict]:
    rows = []
    for gw, m in minutes_by_gw.items():
        row = dict.fromkeys(PLAYER_COLUMNS, 0)
        row.update(element=element, gw=gw, team=1, position=position, n_fix=n_fix if m >= 0 else 0,
                   minutes=max(m, 0), starts=int(m >= 60), apps=int(m > 0), mins60=int(m >= 60))
        rows.append(row)
    return rows


def test_minutes_regular_rotation_and_unused() -> None:
    table = pd.DataFrame(
        _rows(1, {gw: 90 for gw in range(1, 9)})
        + _rows(2, {gw: 0 for gw in range(1, 9)})
        + _rows(3, {1: 90, 2: 90, 3: 90, 4: 90, 5: 0, 6: 0, 7: 0, 8: 0})
    )
    p = minutes_profiles(table)
    assert p[1].p_60 > 0.9 and p[1].minutes > 80
    assert p[2].p_appear < 0.05
    assert p[3].p_60 < 0.35  # recent benchings outweigh older starts


def test_blank_gameweeks_are_ignored_for_minutes() -> None:
    table = pd.DataFrame(_rows(1, {1: 90, 2: 90, 3: -1, 4: 90}))  # -1 = team blank in GW3
    assert minutes_profiles(table)[1].p_60 > 0.9


# ---- rates ------------------------------------------------------------------------------


def test_rates_fall_back_to_position_and_price_prior(season: SeasonData) -> None:
    from app.model.history import player_gameweeks

    history = player_gameweeks(season)
    rates = player_rates(history.iloc[0:0], season.bootstrap.elements)  # no data at all
    fwd = sorted((e for e in season.bootstrap.elements if e.element_type == FWD), key=lambda e: e.start_cost)
    assert rates[fwd[-1].id].xg90 > rates[fwd[0].id].xg90  # pricier forward, higher prior
    gk = next(e for e in season.bootstrap.elements if e.element_type == GKP)
    assert rates[gk.id].saves90 > 0 and rates[gk.id].dc_rate == 0
    assert rates[fwd[0].id].saves90 == 0


# ---- availability -----------------------------------------------------------------------


def _element(season: SeasonData, **changes):
    base = next(e for e in season.bootstrap.elements if e.status == "a")
    return base.model_copy(update=changes)


def _kick(day: int, month: int = 11) -> datetime:
    return datetime(2026, month, day, 15, tzinfo=timezone.utc)


def test_unavailable_status_is_always_zero(season: SeasonData) -> None:
    gone = _element(season, status="u", chance_of_playing_next_round=0, news="Has joined Al Hilal permanently")
    assert availability(gone, _kick(21), 11, 11) == 0
    assert availability(gone, _kick(28), 12, 11) == 0


def test_return_date_from_news(season: SeasonData) -> None:
    posted = datetime(2026, 11, 1, tzinfo=timezone.utc)
    hurt = _element(season, status="i", chance_of_playing_next_round=0,
                    news="Hamstring injury - Expected back 22 Nov", news_added=posted)
    assert availability(hurt, _kick(21), 11, 11) == 0
    assert availability(hurt, _kick(22), 11, 11) == 1
    banned = _element(season, status="s", chance_of_playing_next_round=0, news="Suspended until 29 Nov", news_added=posted)
    assert availability(banned, _kick(28), 12, 11) == 0
    assert availability(banned, _kick(6, 12), 13, 11) == 1


def test_return_date_rolls_into_next_year(season: SeasonData) -> None:
    hurt = _element(season, news="Hamstring injury - Expected back 2 Jan",
                    news_added=datetime(2026, 10, 10, tzinfo=timezone.utc))
    assert return_date(hurt).isoformat() == "2027-01-02"


def test_chance_of_playing_applies_to_next_gw_only(season: SeasonData) -> None:
    doubt = _element(season, status="d", chance_of_playing_next_round=50, news="Knock - 50% chance of playing")
    assert availability(doubt, _kick(21), 11, 11) == 0.5
    assert availability(doubt, _kick(28), 12, 11) == 1.0
    fit = _element(season, chance_of_playing_next_round=None, news="")
    assert availability(fit, _kick(21), 11, 11) == 1.0


# ---- per-fixture points -----------------------------------------------------------------

RULES = ScoringRules(1, 2, 3, 1, -1, {GKP: 10, DEF: 6, MID: 5, FWD: 4}, {GKP: 4, DEF: 4, MID: 1, FWD: 0},
                     {GKP: -1, DEF: -1, MID: 0, FWD: 0}, {GKP: 0, DEF: 2, MID: 2, FWD: 2})
NAILED = MinutesProfile(p_appear=1.0, p_start=1.0, p_60=0.95, minutes=88)
RATES = PlayerRates(xg90=0.5, xa90=0.2, bonus90=0.5, yellow90=0.1, saves90=3.0, dc_rate=0.4)
CTX = FixtureContext(team_goals=1.4, opponent_goals=1.2, team_avg_goals=1.4, team_avg_conceded=1.2, n_team_fixtures=1)


@pytest.mark.parametrize("mean, k", [(0.3, 2), (1.2, 2), (3.0, 3), (5.5, 3)])
def test_expected_floor_div_matches_brute_force(mean: float, k: int) -> None:
    brute = sum((n // k) * math.exp(-mean) * mean**n / math.factorial(n) for n in range(60))
    assert expected_floor_div(mean, k) == pytest.approx(brute, abs=1e-9)


def test_unavailable_player_scores_zero() -> None:
    assert fixture_points(MID, NAILED, RATES, CTX, RULES, available=0) == ZERO


def test_position_specific_points() -> None:
    fwd = fixture_points(FWD, NAILED, RATES, CTX, RULES)
    deff = fixture_points(DEF, NAILED, RATES, CTX, RULES)
    gk = fixture_points(GKP, NAILED, RATES, CTX, RULES)
    assert fwd.clean_sheet == 0 and fwd.goals_conceded == 0
    assert deff.clean_sheet == pytest.approx(0.95 * math.exp(-1.2) * 4)
    assert deff.goals_conceded < 0 and gk.saves > 0 and gk.defensive_contribution == 0
    assert deff.goals == pytest.approx(0.5 * 88 / 90 * 6)


def test_harder_fixture_means_fewer_attacking_points() -> None:
    easy = fixture_points(FWD, NAILED, RATES, CTX, RULES)
    hard = fixture_points(FWD, NAILED, RATES, FixtureContext(0.7, 2.0, 1.4, 1.2, 1), RULES)
    assert hard.goals < easy.goals and hard.total < easy.total


def test_double_gameweek_match_carries_rotation_risk() -> None:
    single = fixture_points(MID, NAILED, RATES, CTX, RULES).total
    double_leg = fixture_points(MID, NAILED, RATES, FixtureContext(1.4, 1.2, 1.4, 1.2, 2), RULES).total
    assert double_leg == pytest.approx(single * DGW_ROTATION)
