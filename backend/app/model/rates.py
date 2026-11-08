"""Per-90 rates (xG, xA, bonus, cards, saves) and the defensive-contribution hit rate.

Each rate is the recent rate pulled toward the player's season rate, which is itself pulled
toward a prior for his position and price. So a player with few minutes looks like a typical
player of his type, and one hot week doesn't dominate.
"""

from dataclasses import dataclass

import pandas as pd

from app.fpl.models import Element
from app.model.scoring import DEF, FWD, GKP, MID

RECENT_WINDOW = 6
SEASON_PSEUDO_MINUTES = 450.0
RECENT_PSEUDO_MINUTES = 360.0
DC_PSEUDO_FIXTURES = 4.0
MIN_MINUTES_FOR_PRIOR = 270
PRICE_FACTOR_LIMITS = (0.4, 2.5)

# Fallback position means (per 90) for when there's no data yet.
FALLBACK = {
    "xg": {GKP: 0.0, DEF: 0.05, MID: 0.15, FWD: 0.35},
    "xa": {GKP: 0.01, DEF: 0.05, MID: 0.12, FWD: 0.12},
    "bonus": {GKP: 0.3, DEF: 0.3, MID: 0.3, FWD: 0.35},
    "yellow": {GKP: 0.03, DEF: 0.15, MID: 0.15, FWD: 0.1},
    "saves": {GKP: 2.8, DEF: 0.0, MID: 0.0, FWD: 0.0},
}
FALLBACK_DC_RATE = {GKP: 0.0, DEF: 0.3, MID: 0.15, FWD: 0.05}
PRICE_SCALED = {"xg", "xa", "bonus"}  # pricier players are expected to return more


@dataclass(frozen=True)
class PlayerRates:
    xg90: float
    xa90: float
    bonus90: float
    yellow90: float
    saves90: float
    dc_rate: float  # chance of hitting the DC threshold in a 60+ minute appearance


def player_rates(players: pd.DataFrame, elements: list[Element]) -> dict[int, PlayerRates]:
    """`players` is the player_gameweeks table filtered to the training GWs."""
    start_cost = {e.id: e.start_cost for e in elements}  # known before the season: no leakage
    position = {e.id: e.element_type for e in elements}
    priors = _position_priors(players)
    by_position: dict[int, list[int]] = {}
    for e in elements:
        by_position.setdefault(e.element_type, []).append(e.start_cost)
    priors["cost"] = {pos: sum(costs) / len(costs) for pos, costs in by_position.items()}

    season = players.groupby("element")[["minutes", "xg", "xa", "bonus", "yellow", "saves", "dc_hits", "mins60"]].sum()
    recent_rows = players[players["n_fix"] > 0].sort_values("gw").groupby("element").tail(RECENT_WINDOW)
    recent = recent_rows.groupby("element")[["minutes", "xg", "xa", "bonus", "yellow", "saves"]].sum()

    out: dict[int, PlayerRates] = {}
    for e in elements:
        pos = position[e.id]
        prior = {k: _prior_for(priors, k, pos, start_cost[e.id]) for k in FALLBACK}
        s = season.loc[e.id] if e.id in season.index else None
        r = recent.loc[e.id] if e.id in recent.index else None
        rates = {}
        for key in FALLBACK:
            season_rate = _shrunk(s, key, prior[key], SEASON_PSEUDO_MINUTES)
            rates[key] = _shrunk(r, key, season_rate, RECENT_PSEUDO_MINUTES)
        dc_prior = priors["dc_rate"].get(pos, FALLBACK_DC_RATE[pos])
        hits, chances = (float(s["dc_hits"]), float(s["mins60"])) if s is not None else (0.0, 0.0)
        dc_rate = (hits + DC_PSEUDO_FIXTURES * dc_prior) / (chances + DC_PSEUDO_FIXTURES)
        out[e.id] = PlayerRates(
            xg90=rates["xg"],
            xa90=rates["xa"],
            bonus90=rates["bonus"],
            yellow90=rates["yellow"],
            saves90=rates["saves"] if pos == GKP else 0.0,
            dc_rate=dc_rate if pos != GKP else 0.0,
        )
    return out


def _shrunk(row: pd.Series | None, key: str, prior_rate: float, pseudo_minutes: float) -> float:
    minutes = float(row["minutes"]) if row is not None else 0.0
    total = float(row[key]) if row is not None else 0.0
    return (total + prior_rate * pseudo_minutes / 90) / (minutes + pseudo_minutes) * 90


def _position_priors(players: pd.DataFrame) -> dict:
    """Minutes-weighted per-90 means by position among regulars."""
    totals = players.groupby(["element", "position"])[
        ["minutes", "xg", "xa", "bonus", "yellow", "saves", "dc_hits", "mins60"]
    ].sum().reset_index()
    regulars = totals[totals["minutes"] >= MIN_MINUTES_FOR_PRIOR]

    priors: dict = {k: {} for k in FALLBACK}
    priors["dc_rate"] = {}
    for pos, grp in regulars.groupby("position"):
        minutes = grp["minutes"].sum()
        for key in FALLBACK:
            priors[key][pos] = float(grp[key].sum() / minutes * 90)
        if grp["mins60"].sum() > 0:
            priors["dc_rate"][pos] = float(grp["dc_hits"].sum() / grp["mins60"].sum())
    return priors


def _prior_for(priors: dict, key: str, pos: int, cost: int) -> float:
    base = priors[key].get(pos, FALLBACK[key][pos])
    if key in PRICE_SCALED and pos in priors["cost"]:
        lo, hi = PRICE_FACTOR_LIMITS
        base *= min(max(cost / priors["cost"][pos], lo), hi)
    return base
