"""No leakage, a faithful FPL benchmark, and the phase 2 gate."""

from datetime import datetime

import pandas as pd
import pytest

from app.model.backtest import backtest, fpl_form, summarise
from app.model.history import SeasonData, player_gameweeks
from app.model.project import project


def test_prediction_for_gw_k_ignores_gw_k_and_later(season: SeasonData) -> None:
    k = 7
    before = project(season, train_through=k - 1, target_gws=[k], use_availability=False)

    live = {gw: lv.model_copy(deep=True) for gw, lv in season.live.items()}
    for gw in [g for g in live if g >= k]:
        for el in live[gw].elements:
            el.stats.total_points, el.stats.minutes, el.stats.expected_goals = 99, 90, 5.0
    bootstrap = season.bootstrap.model_copy(deep=True)
    # Season totals in bootstrap are "the future" for a GW7 prediction: they mustn't be used.
    bootstrap.elements = [
        e.model_copy(update={"total_points": 999, "expected_goals": 99.0, "minutes": 9999, "form": 20.0, "ep_next": 20.0})
        for e in bootstrap.elements
    ]
    after = project(SeasonData(bootstrap, season.fixtures, live), train_through=k - 1, target_gws=[k], use_availability=False)
    pd.testing.assert_frame_equal(before, after)


def test_fpl_form_replica_matches_bootstrap_exactly(season_with_current: SeasonData, snapshot_time: datetime) -> None:
    history = player_gameweeks(season_with_current)
    replica = fpl_form(season_with_current, history, snapshot_time)
    actual = {e.id: e.form for e in season_with_current.bootstrap.elements}
    mismatches = [el for el, form in actual.items() if abs(replica.get(el, 0.0) - form) > 0.05]
    assert mismatches == []


def test_fpl_ep_next_is_form_times_chance(season: SeasonData) -> None:
    """Why the form replica is a fair stand-in for historical ep_next."""
    matches = sum(
        abs(e.ep_next - round(e.form * (e.chance_of_playing_next_round if e.chance_of_playing_next_round is not None else 100) / 100, 1)) <= 0.1
        for e in season.bootstrap.elements
    )
    assert matches / len(season.bootstrap.elements) > 0.99


@pytest.fixture(scope="module")
def results(season: SeasonData) -> pd.DataFrame:
    return backtest(season, range(4, max(season.live) + 1))


def test_gate_model_is_no_worse_than_fpl_ep(results: pd.DataFrame) -> None:
    summary = summarise(results)
    for population in ("played", "had_fixture"):
        row = summary.loc[population]
        assert row["mae_model"] <= row["mae_fpl_ep"], population
        assert row["mae_model"] <= row["mae_ppg"], population


def test_model_is_roughly_calibrated(results: pd.DataFrame) -> None:
    row = summarise(results).loc["had_fixture"]
    assert abs(row["mean_model"] - row["mean_actual"]) / row["mean_actual"] < 0.15
