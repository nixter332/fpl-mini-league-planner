from app.model.history import SeasonData, player_gameweeks, team_matches
from app.model.scoring import DEF, DC_THRESHOLDS, FWD, GKP, MID, ScoringRules


def test_scoring_rules_from_game_config(season: SeasonData) -> None:
    rules = ScoringRules.from_game_config(season.bootstrap.game_config.scoring)
    assert rules.goals_scored == {GKP: 10, DEF: 6, MID: 5, FWD: 4}
    assert rules.clean_sheets == {GKP: 4, DEF: 4, MID: 1, FWD: 0}
    assert rules.goals_conceded == {GKP: -1, DEF: -1, MID: 0, FWD: 0}
    assert rules.defensive_contribution == {GKP: 0, DEF: 2, MID: 2, FWD: 2}
    assert (rules.assists, rules.short_play, rules.long_play, rules.saves) == (3, 1, 2, 1)


def test_player_gameweeks_matches_live_stats(season: SeasonData) -> None:
    history = player_gameweeks(season)
    assert set(history["gw"]) == set(season.live)
    gw9 = history[history["gw"] == 9].set_index("element")
    live9 = {el.id: el.stats for el in season.live[9].elements}
    for element in list(gw9.index)[:50]:
        assert gw9.loc[element, "minutes"] == live9[element].minutes
        assert gw9.loc[element, "points"] == live9[element].total_points
    # No doubles or blanks so far this season: every registered player has one fixture.
    assert set(history["n_fix"]) == {1}
    assert (history["apps"] <= history["n_fix"]).all()
    assert (history["mins60"] <= history["apps"]).all()


def test_dc_hits_agree_with_thresholds(season: SeasonData) -> None:
    history = player_gameweeks(season)
    hits = history[history["dc_hits"] > 0]
    assert len(hits) > 0
    assert (hits["position"] != GKP).all()
    for _, row in hits.iterrows():
        assert row["dc"] >= DC_THRESHOLDS[row["position"]]


def test_team_matches_have_both_sides_xg(season: SeasonData) -> None:
    history = player_gameweeks(season)
    matches = team_matches(season, history)
    assert len(matches[matches["gw"] == 9]) == 10
    # A side's xG (from the opponent's xGC) agrees with the sum of its players' xG (each rounded to 0.01).
    gw9 = history[history["gw"] == 9]
    xg_by_team = gw9[gw9["team"] >= 0].groupby("team")["xg"].sum()
    for _, m in matches[matches["gw"] == 9].iterrows():
        assert abs(m["xg_home"] - xg_by_team[m["home"]]) < 0.15
        assert abs(m["xg_away"] - xg_by_team[m["away"]]) < 0.15
